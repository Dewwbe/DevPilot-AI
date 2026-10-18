#!/usr/bin/env bash
# Install the cluster add-ons DevPilot needs on a fresh EKS cluster (run once per cluster):
#   ingress-nginx (NLB), cert-manager (TLS), Secrets Store CSI driver + AWS provider (Secrets
#   Manager), metrics-server (HPA), kube-prometheus-stack (Prometheus + Grafana).
# Prereqs: kubectl pointed at the cluster (terraform output kubeconfig_command), helm 3.
# Chart versions are left unpinned for convenience; pin them (--version) before relying on this
# in production.
set -euo pipefail

command -v helm >/dev/null || { echo "helm is required"; exit 1; }
kubectl cluster-info >/dev/null || { echo "kubectl cannot reach a cluster"; exit 1; }

helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm repo add jetstack https://charts.jetstack.io
helm repo add secrets-store-csi-driver https://kubernetes-sigs.github.io/secrets-store-csi-driver/charts
helm repo add aws-secrets-manager https://aws.github.io/secrets-store-csi-driver-provider-aws
helm repo add metrics-server https://kubernetes-sigs.github.io/metrics-server/
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

echo "==> ingress-nginx (AWS NLB)"
helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx -n ingress-nginx --create-namespace \
  --set controller.service.annotations."service\.beta\.kubernetes\.io/aws-load-balancer-type"=nlb \
  --set controller.metrics.enabled=true

echo "==> cert-manager"
helm upgrade --install cert-manager jetstack/cert-manager -n cert-manager --create-namespace \
  --set crds.enabled=true

echo "==> Secrets Store CSI driver (+ sync to Kubernetes Secrets) and the AWS provider"
helm upgrade --install csi-secrets-store secrets-store-csi-driver/secrets-store-csi-driver \
  -n kube-system --set syncSecret.enabled=true --set enableSecretRotation=true
helm upgrade --install secrets-provider-aws aws-secrets-manager/secrets-store-csi-driver-provider-aws \
  -n kube-system

echo "==> metrics-server (needed by the API HorizontalPodAutoscaler)"
helm upgrade --install metrics-server metrics-server/metrics-server -n kube-system

echo "==> kube-prometheus-stack (Prometheus, Alertmanager, Grafana)"
helm upgrade --install monitoring prometheus-community/kube-prometheus-stack -n monitoring \
  --create-namespace \
  --set prometheus.prometheusSpec.serviceMonitorSelectorNilUsesHelmValues=false \
  --set prometheus.prometheusSpec.ruleSelectorNilUsesHelmValues=false \
  --set grafana.sidecar.dashboards.enabled=true \
  --set grafana.sidecar.dashboards.searchNamespace=ALL

echo
echo "Done. Ingress address (create a DNS CNAME for your host to it):"
kubectl -n ingress-nginx get svc ingress-nginx-controller \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}{"\n"}'
echo "Grafana admin password:  kubectl -n monitoring get secret monitoring-grafana -o jsonpath='{.data.admin-password}' | base64 -d"
echo "Grafana UI:              kubectl -n monitoring port-forward svc/monitoring-grafana 3000:80"
