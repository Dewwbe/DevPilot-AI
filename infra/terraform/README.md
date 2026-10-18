# Terraform — AWS (ECR + ECS Fargate)

See [docs/DEPLOY-AWS.md](../../docs/DEPLOY-AWS.md).

Creates only: two ECR repositories, one ECS Fargate cluster/service (web, api, worker, Postgres
and Redis as containers in one task), a security group, an execution role and a log group.
