{{- define "devpilot.labels" -}}
app.kubernetes.io/name: devpilot
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end }}

{{/* Selector labels for one component: include "devpilot.selector" (dict "root" . "component" "api") */}}
{{- define "devpilot.selector" -}}
app.kubernetes.io/name: devpilot
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end }}

{{- define "devpilot.image" -}}
{{- $r := .root.Values.image.registry -}}
{{- if $r }}{{ $r }}/{{ end }}{{ .img.repository }}:{{ .img.tag }}
{{- end }}

{{/* JSON key -> env var map, including the optional GitHub App credentials. */}}
{{- define "devpilot.secretMap" -}}
{{- $m := deepCopy .Values.secrets.envFromJson -}}
{{- if .Values.secrets.githubApp.enabled -}}
{{- $_ := set $m "github_app_id" "DEVPILOT_GITHUB_APP_ID" -}}
{{- $_ := set $m "github_app_private_key" "DEVPILOT_GITHUB_APP_PRIVATE_KEY" -}}
{{- $_ := set $m "github_app_installation_id" "DEVPILOT_GITHUB_APP_INSTALLATION_ID" -}}
{{- end -}}
{{- if .Values.secrets.oauth.enabled -}}
{{- $_ := set $m "github_oauth_client_id" "DEVPILOT_GITHUB_OAUTH_CLIENT_ID" -}}
{{- $_ := set $m "github_oauth_client_secret" "DEVPILOT_GITHUB_OAUTH_CLIENT_SECRET" -}}
{{- $_ := set $m "session_secret" "DEVPILOT_SESSION_SECRET" -}}
{{- end -}}
{{- toYaml $m -}}
{{- end }}

{{- define "devpilot.podSecurityContext" -}}
runAsNonRoot: true
runAsUser: 10001
runAsGroup: 10001
seccompProfile: { type: RuntimeDefault }
{{- end }}

{{- define "devpilot.containerSecurityContext" -}}
allowPrivilegeEscalation: false
readOnlyRootFilesystem: true
capabilities: { drop: ["ALL"] }
{{- end }}

{{/* Config + (optionally) synced secrets as environment. */}}
{{- define "devpilot.envFrom" -}}
- configMapRef: { name: {{ .Release.Name }}-config }
{{- if .Values.secrets.enabled }}
- secretRef: { name: {{ .Release.Name }}-secrets }
{{- end }}
{{- end }}

{{/* The CSI volume must be mounted by a pod for the synced Secret to exist. */}}
{{- define "devpilot.secretsVolume" -}}
{{- if .Values.secrets.enabled }}
- name: secrets-store
  csi:
    driver: secrets-store.csi.k8s.io
    readOnly: true
    volumeAttributes:
      secretProviderClass: {{ .Release.Name }}-secrets
{{- end }}
{{- end }}

{{- define "devpilot.secretsMount" -}}
{{- if .Values.secrets.enabled }}
- { name: secrets-store, mountPath: /mnt/secrets-store, readOnly: true }
{{- end }}
{{- end }}
