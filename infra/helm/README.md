# Helm chart

`devpilot/` deploys the API, Celery worker, dashboard, a pre-upgrade migration Job, ingress with
cert-manager TLS, an HPA on the API, and optional ServiceMonitors. Secrets are read from AWS
Secrets Manager through the Secrets Store CSI driver; nothing secret lives in the chart.

```bash
helm lint devpilot -f devpilot/values-prod.yaml --set config.DEVPILOT_REDIS_URL=redis://x:6379/0
helm template devpilot devpilot -f devpilot/values-prod.yaml --set config.DEVPILOT_REDIS_URL=redis://x:6379/0 \
  | kubeconform -strict -summary -
helm upgrade --install devpilot devpilot -f devpilot/values-dev.yaml -n devpilot --create-namespace \
  --set image.registry=<account>.dkr.ecr.<region>.amazonaws.com \
  --set image.api.tag=<tag> --set image.web.tag=<tag> \
  --set config.DEVPILOT_REDIS_URL=<redis url> \
  --set serviceAccount.roleArn=<app_role_arn> --set certManager.email=<you@example.com>
```

Full procedure: [docs/DEPLOY-K8S.md](../../docs/DEPLOY-K8S.md). The legacy kustomize base in
`../k8s/base` is kept as a plain-manifest reference and is still validated in CI.
