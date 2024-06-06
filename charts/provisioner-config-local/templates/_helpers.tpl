{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "provisioner-config-local.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "provisioner-config-local.labels" -}}
helm.sh/chart: {{ include "provisioner-config-local.chart" . }}
{{ include "provisioner-config-local.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "provisioner-config-local.selectorLabels" -}}
app.kubernetes.io/name: {{ include "provisioner-config-local.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

