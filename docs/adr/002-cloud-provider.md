# ADR-002: Cloud provider

**Status:** Accepted — AWS (Phase 0)

## Decision

Deploy on **AWS** using only **ECR** (images) and **ECS Fargate** (compute). Postgres and Redis run
as sidecar containers in the same task, mirroring docker-compose.

## Reasoning

- ECS Fargate has no control plane to pay for or operate (EKS costs ~$73/month before any node).
- Keeping to two AWS services minimises cost and surface area for a solo project.
- The `infra/k8s` manifests stay as a portable reference.

## Consequences

- Data is ephemeral: it is lost when the task restarts. Acceptable for dev and demos.
- Later phases can swap in RDS, ElastiCache, an ALB, Secrets Manager and CI/CD by OIDC without
  changing the images.
- Azure was not chosen: no existing credits or employer stack pointed that way.
