# ADR-003: Kubernetes on EKS, packaged as a Helm chart

**Status:** Accepted (Phase 3)

## Context
ADR-002 chose AWS and started on ECS Fargate for the cheapest possible demo. Phase 3 asks for a
production-shaped platform: managed database and cache, secrets from a secrets manager, TLS
ingress, autoscaling, and observability. The role this project targets also lists Kubernetes.

## Decision
Run on **Amazon EKS**, deployed with a **Helm chart** (`infra/helm/devpilot`, values per
environment), backed by **RDS PostgreSQL**, **ElastiCache Redis** and **Secrets Manager**,
provisioned by Terraform (`infra/terraform-eks`, a separate root module with its own state).
ECS Fargate (`infra/terraform`) stays as the low-cost demo option and shares the same images.

Key choices inside that decision:
- **Secrets:** Secrets Store CSI driver + AWS provider, with an IRSA role limited to one secret.
  The driver's "sync as Kubernetes Secret" feature exposes values to `envFrom` at runtime. No
  secret is committed, templated into values, or created by a script.
- **Ingress and TLS:** ingress-nginx (NLB) with cert-manager and Let's Encrypt. Two Ingress
  objects: a public one (webhook, health) and one behind basic auth (everything else).
- **Migrations:** a Helm `pre-upgrade` Job runs `alembic upgrade head`; API pods run with
  `DEVPILOT_AUTO_MIGRATE=false` so replicas never race on the schema.
- **Autoscaling:** HPA on API CPU (metrics-server), with a PodDisruptionBudget.
- **Worker pool:** Celery `-P threads` so one process records every task's Prometheus metrics.

## Alternatives considered
- **Stay on ECS Fargate only:** simplest and cheaper, but no Kubernetes story, no CSI secrets
  pattern, weaker ingress/TLS/HPA/observability options.
- **AKS:** equivalent capability; AWS was already chosen in ADR-002 and ECR is in use.
- **Raw kustomize manifests:** kept as a reference, but values per environment, hooks and
  conditional resources (CRDs, dashboards) are much cleaner in Helm.
- **External Secrets Operator:** a good alternative to the CSI driver; CSI was chosen because it
  mounts directly from Secrets Manager with IRSA and needs no extra controller state.

## Consequences
- Cost: an EKS control plane (about $73/month) plus nodes, NAT, RDS and ElastiCache. Expect
  roughly $200/month for the dev profile. Destroy it when not demoing.
- Operational surface grows: add-ons (`scripts/eks-addons.sh`) must be installed and kept
  current, and chart versions should be pinned.
- The web image moved to `nginx-unprivileged` so every pod can run non-root with a read-only
  root filesystem.
