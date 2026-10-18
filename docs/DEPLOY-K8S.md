# Deploying to Kubernetes (EKS + Helm)

End state: a public HTTPS URL on EKS, secrets from Secrets Manager, managed Postgres and Redis,
Prometheus and Grafana dashboards, and logs in CloudWatch. Commands are PowerShell, from the repo
root unless noted. Cost is roughly $200/month while running, so destroy it when you are done
(section 10).

Nothing in this procedure has been run against a real AWS account yet; the Terraform and chart are
validated (`terraform validate`, `helm lint`, `kubeconform`) but expect small fixes on first use.

## 0. Prerequisites
- AWS CLI configured (`aws sts get-caller-identity`) with permissions to create VPC, EKS, RDS,
  ElastiCache, IAM and Secrets Manager resources.
- `terraform` 1.6+, `kubectl`, `helm` 3 (`winget install Kubernetes.kubectl Helm.Helm`).
- Images in ECR (`devpilot-api`, `devpilot-web`). The `publish.yml` workflow does this on every
  merge to `main` (tag = commit SHA); to do it by hand see [DEPLOY-AWS.md](DEPLOY-AWS.md) step 2.
  Terraform for ECR and the publish role lives in `infra/terraform` (apply at least
  `-target=aws_ecr_repository.repo`).
- A DNS name you control for the app (for example `devpilot.example.com`).

## 1. Provision the cloud resources
```powershell
cd infra\terraform-eks
Copy-Item terraform.tfvars.example terraform.tfvars
# edit: admin_cidrs = ["<your public IP>/32"], environment = "dev" or "prod"
terraform init
terraform plan -out tfplan        # read it: VPC, EKS, RDS, ElastiCache, Secrets Manager, IRSA role
terraform apply tfplan            # about 20 minutes (EKS and RDS are the slow parts)
terraform output
```

## 2. Connect kubectl
```powershell
terraform output -raw kubeconfig_command | Invoke-Expression
kubectl get nodes                 # expect 2 Ready nodes
cd ..\..
```

## 3. Install cluster add-ons (once per cluster)
Needs Git Bash or WSL for the shell script:
```bash
./scripts/eks-addons.sh
```
Installs ingress-nginx (AWS NLB), cert-manager, the Secrets Store CSI driver with the AWS
provider, metrics-server and kube-prometheus-stack. It prints the NLB hostname at the end.
Create a DNS **CNAME** from your host name to that hostname.

## 4. Put the real secrets in Secrets Manager
Terraform created `devpilot-<env>/app` containing the database URL, a random webhook secret and
`REPLACE_ME` placeholders. Update the placeholders (the value is one JSON object, so merge, do
not replace):
```powershell
$id = "devpilot-dev/app"
$s  = aws secretsmanager get-secret-value --secret-id $id --query SecretString --output text | ConvertFrom-Json
$s.anthropic_api_key = "<your Anthropic key>"
$s.github_token      = "<fine-grained PAT, read-only Actions + Contents>"
# dashboard login (bcrypt htpasswd line), e.g. user admin:
$s.basic_auth_htpasswd = (docker run --rm httpd:2.4-alpine htpasswd -nbB admin "<password>").Trim()
$s | ConvertTo-Json -Compress | Set-Content secret.json -Encoding ascii
aws secretsmanager put-secret-value --secret-id $id --secret-string file://secret.json
Remove-Item secret.json
```
The GitHub App keys (`github_app_*`) are optional; see section 8.

## 5. Install DevPilot
```powershell
cd infra\terraform-eks
$registry = terraform output -raw ecr_registry
$redis    = terraform output -raw redis_url
$role     = terraform output -raw app_role_arn
cd ..\..

helm upgrade --install devpilot infra/helm/devpilot -n devpilot --create-namespace `
  -f infra/helm/devpilot/values-dev.yaml `
  --set image.registry=$registry --set image.api.tag=<sha-or-tag> --set image.web.tag=<sha-or-tag> `
  --set config.DEVPILOT_REDIS_URL=$redis --set serviceAccount.roleArn=$role `
  --set ingress.host=devpilot.example.com --set certManager.email=you@example.com
```
Use `values-prod.yaml` for production (HA, autoscaling, trusted certificates, ServiceMonitors).
The first install creates the Let's Encrypt `ClusterIssuer`s (`certManager.createClusterIssuers`);
for later releases into the same cluster set it to `false`.

What happens: the `migrate` Job runs `alembic upgrade head`, then the api, worker and web
Deployments start; the CSI driver mounts the secret and syncs it for `envFrom`; cert-manager
requests a certificate for the host.

## 6. Verify
```powershell
kubectl -n devpilot get pods                       # all Running; migrate Job Completed then removed
kubectl -n devpilot rollout status deploy/devpilot-api
kubectl -n devpilot get certificate                # READY=True after DNS resolves (a few minutes)
curl.exe -fsS https://devpilot.example.com/readyz  # {"status":"ready"}
```
Open `https://devpilot.example.com`, sign in with the basic-auth user, and run the Diagnose page.
Autoscaling: `kubectl -n devpilot get hpa` (TARGETS should show a percentage, not `<unknown>`).

## 7. Observability
```powershell
kubectl -n monitoring port-forward svc/monitoring-grafana 3000:80
# admin password: kubectl -n monitoring get secret monitoring-grafana -o jsonpath='{.data.admin-password}'
#                 (base64 decode it)
```
Open http://localhost:3000 and the **DevPilot AI** dashboard (installed with the chart when
`monitoring.serviceMonitor=true`): diagnosis latency, estimated spend per day, tokens, failure
categories, approval rate, breaker state, fallback share, webhook results and API latency. Alerts
are in Prometheus (`kubectl -n monitoring port-forward svc/monitoring-kube-prometheus-prometheus 9090`).
Application logs are in CloudWatch Logs under the cluster's `/aws/containerinsights/...` groups.

If panels are empty, send some traffic (Diagnose page) and check Prometheus targets for
`devpilot-api` and `devpilot-worker`.

## 8. GitHub App for pull requests (task 3.9)
1. GitHub > Settings > Developer settings > GitHub Apps > **New GitHub App**. Name `DevPilot AI`.
   Webhook: off. Repository permissions: **Contents: Read and write**, **Pull requests: Read and
   write** (Metadata read is automatic). Nothing else.
2. Create it, note the **App ID**, then **Generate a private key** (a `.pem` file).
3. **Install App** on the demo repository only; note the installation id from the URL
   (`.../settings/installations/<id>`).
4. Add to the Secrets Manager JSON (section 4): `github_app_id`, `github_app_installation_id`, and
   `github_app_private_key` (the PEM text; JSON encoding handles the newlines).
5. Upgrade the release with `--set secrets.githubApp.enabled=true`.

Then, after approving a fix with a patch: `POST /api/fixes/<id>/open-pr` opens a PR from a new
`devpilot/fix-xxxxxxxx` branch. It never touches the default branch and never merges. Patches that
change `.github/workflows/` are rejected by GitHub because the App has no `workflows` permission.

## 9. Upgrades, rollbacks, migrations
```powershell
helm upgrade devpilot infra/helm/devpilot -n devpilot -f infra/helm/devpilot/values-prod.yaml --reuse-values --set image.api.tag=<new> --set image.web.tag=<new>
helm history devpilot -n devpilot
helm rollback devpilot <revision> -n devpilot      # does not undo database migrations
```
Migrations run before every upgrade, so write them as backward compatible (add columns, do not
drop or rename in the same release). New migration: add a guarded file under
`backend/alembic/versions/` and bump the revision id.

## 10. Tear down (stop the bill)
Order matters: delete the Helm releases first so the cluster removes the load balancer, otherwise
the VPC cannot be destroyed.
```powershell
helm uninstall devpilot -n devpilot
helm uninstall ingress-nginx -n ingress-nginx
helm uninstall monitoring -n monitoring
cd infra\terraform-eks ; terraform destroy
```

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| `ImagePullBackOff` | The tag does not exist in ECR or `image.registry` is wrong. Check `aws ecr describe-images --repository-name devpilot-api` |
| Pods stuck `ContainerCreating` with CSI errors | IRSA role ARN wrong or the secret id/keys differ. `kubectl -n devpilot describe pod <pod>`; confirm `serviceAccount.roleArn` and that every JSON key in `secrets.envFromJson` exists in the secret |
| Migration Job fails | `kubectl -n devpilot logs job/devpilot-migrate`. Usually the database URL secret or the RDS security group (nodes must reach port 5432) |
| Certificate stays `False` | DNS CNAME not pointing at the NLB yet, or Let's Encrypt rate limit (use `values-dev.yaml` = staging issuer while testing). `kubectl describe certificate,order,challenge -n devpilot` |
| HPA shows `<unknown>` | metrics-server is not installed or pods have no CPU requests |
| 401 on every page | Expected (basic auth). Check `basic_auth_htpasswd` is a bcrypt htpasswd line |
| Webhook returns 503 | `github_webhook_secret` missing from the secret JSON |
| Dashboard panels empty | `monitoring.serviceMonitor` not enabled, or Prometheus lacks the CRDs; check the targets page |
