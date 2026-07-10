{{/* Common name + label helpers for the polaris-re chart. */}}

{{- define "polaris-re.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "polaris-re.fullname" -}}
{{- printf "%s-api" (include "polaris-re.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "polaris-re.labels" -}}
app.kubernetes.io/name: {{ include "polaris-re.name" . }}
app.kubernetes.io/component: api
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end -}}

{{- define "polaris-re.selectorLabels" -}}
app.kubernetes.io/name: {{ include "polaris-re.name" . }}
app.kubernetes.io/component: api
{{- end -}}
