# Running DevPilot AI: locally and on AWS (ECR + ECS Fargate only)

Commands are PowerShell, run from the repo root.

## 1. Run locally (roadmap tasks 0.2 and 0.4)

Prerequisite: Docker Desktop is running ("Engine running").

```powershell
Copy-Item .env.example .env
# Edit .env: DEVPILOT_ANTHROPIC_API_KEY=...  DEVPILOT_GITHUB_TOKEN=...
docker compose up --build -d
docker compose ps
```

| Check | URL | Expected |
|---|---|---|
| Liveness | http://localhost:8000/healthz | `{"status":"ok"}` |
| Readiness | http://localhost:8000/readyz | `{"status":"ready"}` |
| API docs | http://localhost:8000/docs | Swagger UI |
| Dashboard | http://localhost:8080 | React app |

Logs: `docker compose logs -f api`. Stop: `docker compose down` (add `-v` to wipe the database).
Without an Anthropic key the diagnoser falls back to heuristics.

Backend tests without Docker: `cd backend; pip install -e ".[dev]"; pytest -q; ruff check .`

## 2. Deploy to AWS (ECR + ECS only)

What gets created: 2 ECR repositories, 1 ECS Fargate service running one task with five containers
(web, api, worker, Postgres, Redis), a security group, an ECS execution role and a log group.
No RDS, ElastiCache, load balancer, Secrets Manager or OIDC.

### Prerequisites
`aws --version`, `terraform -version` work in a new terminal; `aws configure` done;
`aws sts get-caller-identity` prints your account; Docker Desktop running.

### Step 1: configure variables
```powershell
cd infra\terraform
Copy-Item terraform.tfvars.example terraform.tfvars
$ip = (Invoke-RestMethod https://checkip.amazonaws.com).Trim()
"Your IP: $ip/32"
```
Edit `terraform.tfvars`: set `allowed_cidr` to your IP with `/32`, and your two keys.
The file is gitignored. The keys end up in the task definition and local Terraform state, so this
is for dev only.

### Step 2: create ECR and push the images
```powershell
terraform init
terraform apply -target=aws_ecr_repository.repo
cd ..\..

$region  = "us-east-1"
$account = aws sts get-caller-identity --query Account --output text
$reg     = "$account.dkr.ecr.$region.amazonaws.com"
aws ecr get-login-password --region $region | docker login --username AWS --password-stdin $reg

docker build -t "$reg/devpilot-api:latest" backend
docker build -t "$reg/devpilot-web:latest" frontend
docker push "$reg/devpilot-api:latest"
docker push "$reg/devpilot-web:latest"
```

### Step 3: create the ECS service
```powershell
cd infra\terraform
terraform apply
```

### Step 4: find the app's address
The task has no load balancer, so its public IP changes on every restart:
```powershell
$task = aws ecs list-tasks --cluster devpilot-dev --service-name app --query "taskArns[0]" --output text
$eni  = aws ecs describe-tasks --cluster devpilot-dev --tasks $task --query "tasks[0].attachments[0].details[?name=='networkInterfaceId'].value" --output text
$ip   = aws ec2 describe-network-interfaces --network-interface-ids $eni --query "NetworkInterfaces[0].Association.PublicIp" --output text
"http://${ip}:8080"
```
Open that URL for the dashboard; `/api/repositories` should return `[]`. (nginx only proxies
`/api/*`, so `/healthz` is not reachable from outside.) Logs: `aws logs tail /ecs/devpilot-dev --follow`.

### Redeploy after code changes
Rebuild and push the `:latest` images (step 2), then:
```powershell
aws ecs update-service --cluster devpilot-dev --service app --force-new-deployment
```

### Stop paying
- Pause compute: `terraform apply -var desired_count=0`
- Remove everything: `terraform destroy`

Fargate (1 vCPU, 2 GB) is roughly $35/month if left running 24/7; ECR storage is pennies.

## Limits of this setup
- Postgres and Redis live inside the task: **all data is lost whenever the task restarts.**
- Public IP changes on restart and the app is HTTP only.
- No login on the dashboard; `allowed_cidr` restricts access to your IP. Keep it that way.
- Tables are created at startup (`create_all`); Alembic is roadmap task 1.7.
- Terraform state is local. Do not commit `terraform.tfstate` (already gitignored).
