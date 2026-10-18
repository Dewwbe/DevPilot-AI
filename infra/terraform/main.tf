locals {
  name = "devpilot-${var.environment}"
}

# Minimal footprint: ECR + one ECS Fargate service. Postgres and Redis run as sidecar containers
# in the same task (like docker-compose), so there is no RDS/ElastiCache/ALB. Data is ephemeral.
# Uses the default VPC; the task gets a public IP, reachable only from var.allowed_cidr.
data "aws_vpc" "default" { default = true }

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# ---------------- ECR ----------------
resource "aws_ecr_repository" "repo" {
  for_each             = toset(["api", "web"])
  name                 = "devpilot-${each.key}"
  image_tag_mutability = "MUTABLE"
  force_delete         = true
  image_scanning_configuration { scan_on_push = true }
}

resource "aws_ecr_lifecycle_policy" "repo" {
  for_each   = aws_ecr_repository.repo
  repository = each.value.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 10 images"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 10 }
      action       = { type = "expire" }
    }]
  })
}

# ---------------- Networking ----------------
resource "aws_security_group" "app" {
  name_prefix = "${local.name}-"
  vpc_id      = data.aws_vpc.default.id
  ingress {
    description = "Dashboard (nginx proxies /api to the API)"
    from_port   = 8080
    to_port     = 8080
    protocol    = "tcp"
    cidr_blocks = [var.allowed_cidr]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  lifecycle { create_before_destroy = true }
}

# ---------------- IAM (ECS needs this to pull from ECR and write logs) ----------------
data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "execution" {
  name               = "${local.name}-ecs-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# ---------------- Logs + cluster ----------------
resource "aws_cloudwatch_log_group" "app" {
  name              = "/ecs/${local.name}"
  retention_in_days = 7
}

resource "aws_ecs_cluster" "main" {
  name = local.name
}

# ---------------- Task: web + api + worker + postgres + redis ----------------
resource "random_password" "db" {
  length  = 24
  special = false
}

locals {
  api_image = "${aws_ecr_repository.repo["api"].repository_url}:${var.image_tag}"
  web_image = "${aws_ecr_repository.repo["web"].repository_url}:${var.image_tag}"

  app_env = [
    { name = "DEVPILOT_ENV", value = var.environment },
    { name = "DEVPILOT_DATABASE_URL", value = "postgresql+psycopg://devpilot:${random_password.db.result}@localhost:5432/devpilot" },
    { name = "DEVPILOT_REDIS_URL", value = "redis://localhost:6379/0" },
    { name = "DEVPILOT_CLAUDE_MODEL", value = var.claude_model },
    { name = "DEVPILOT_ANTHROPIC_API_KEY", value = var.anthropic_api_key },
    { name = "DEVPILOT_GITHUB_TOKEN", value = var.github_token },
  ]

  log = { for c in ["web", "api", "worker", "postgres", "redis"] : c => {
    logDriver = "awslogs"
    options = {
      awslogs-group         = aws_cloudwatch_log_group.app.name
      awslogs-region        = var.region
      awslogs-stream-prefix = c
    }
  } }
}

resource "aws_ecs_task_definition" "app" {
  family                   = local.name
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 1024
  memory                   = 2048
  execution_role_arn       = aws_iam_role.execution.arn

  container_definitions = jsonencode([
    {
      name             = "postgres"
      image            = "postgres:16-alpine"
      essential        = true
      environment      = [
        { name = "POSTGRES_USER", value = "devpilot" },
        { name = "POSTGRES_PASSWORD", value = random_password.db.result },
        { name = "POSTGRES_DB", value = "devpilot" },
      ]
      healthCheck = {
        command  = ["CMD-SHELL", "pg_isready -U devpilot"]
        interval = 5
        timeout  = 3
        retries  = 10
      }
      logConfiguration = local.log["postgres"]
    },
    {
      name             = "redis"
      image            = "redis:7-alpine"
      essential        = true
      logConfiguration = local.log["redis"]
    },
    {
      name        = "api"
      image       = local.api_image
      essential   = true
      environment = local.app_env
      dependsOn = [
        { containerName = "postgres", condition = "HEALTHY" },
        { containerName = "redis", condition = "START" },
      ]
      logConfiguration = local.log["api"]
    },
    {
      name        = "worker"
      image       = local.api_image
      essential   = true
      command     = ["celery", "-A", "app.workers.celery_app", "worker", "--loglevel=info", "--concurrency=2"]
      environment = local.app_env
      dependsOn = [
        { containerName = "postgres", condition = "HEALTHY" },
        { containerName = "redis", condition = "START" },
      ]
      logConfiguration = local.log["worker"]
    },
    {
      name         = "web"
      image        = local.web_image
      essential    = true
      portMappings = [{ containerPort = 8080 }]
      # Containers in one Fargate task share localhost.
      environment      = [{ name = "API_UPSTREAM", value = "localhost:8000" }]
      dependsOn        = [{ containerName = "api", condition = "START" }]
      logConfiguration = local.log["web"]
    },
  ])
}

resource "aws_ecs_service" "app" {
  name            = "app"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.app.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"
  network_configuration {
    subnets          = data.aws_subnets.default.ids
    security_groups  = [aws_security_group.app.id]
    assign_public_ip = true
  }
}
