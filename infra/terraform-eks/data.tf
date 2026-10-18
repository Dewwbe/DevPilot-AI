# ---------------- Managed PostgreSQL (RDS) ----------------
resource "random_password" "db" {
  length  = 32
  special = false
}

resource "aws_security_group" "db" {
  name_prefix = "${local.name}-db-"
  vpc_id      = module.vpc.vpc_id
  ingress {
    description     = "PostgreSQL from the EKS nodes"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [module.eks.node_security_group_id]
  }
  lifecycle { create_before_destroy = true }
}

resource "aws_db_instance" "postgres" {
  identifier             = local.name
  engine                 = "postgres"
  engine_version         = "16"
  instance_class         = var.db_instance_class
  allocated_storage      = 20
  max_allocated_storage  = 100
  storage_type           = "gp3"
  storage_encrypted      = true
  db_name                = "devpilot"
  username               = "devpilot"
  password               = random_password.db.result
  db_subnet_group_name   = module.vpc.database_subnet_group_name
  vpc_security_group_ids = [aws_security_group.db.id]
  publicly_accessible    = false

  multi_az                     = local.is_prod
  backup_retention_period      = local.is_prod ? 14 : 3
  deletion_protection          = local.is_prod
  skip_final_snapshot          = !local.is_prod
  final_snapshot_identifier    = local.is_prod ? "${local.name}-final" : null
  performance_insights_enabled = true
}

# ---------------- Managed Redis (ElastiCache) ----------------
resource "aws_security_group" "redis" {
  name_prefix = "${local.name}-redis-"
  vpc_id      = module.vpc.vpc_id
  ingress {
    description     = "Redis from the EKS nodes"
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [module.eks.node_security_group_id]
  }
  lifecycle { create_before_destroy = true }
}

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id = local.name
  description          = "DevPilot broker and result backend"
  engine               = "redis"
  engine_version       = "7.1"
  node_type            = "cache.t4g.micro"
  port                 = 6379

  num_cache_clusters         = local.is_prod ? 2 : 1
  automatic_failover_enabled = local.is_prod
  multi_az_enabled           = local.is_prod

  subnet_group_name  = module.vpc.elasticache_subnet_group_name
  security_group_ids = [aws_security_group.redis.id]

  at_rest_encryption_enabled = true
  # In-transit TLS is off because the app uses a plain redis:// URL inside the private subnets.
  transit_encryption_enabled = false
}
