{{- define "platform-app.name" -}}{{ default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}{{- end }}
{{- define "platform-app.labels" -}}
app.kubernetes.io/name: {{ include "platform-app.name" . }}
app.kubernetes.io/part-of: voice-command-platform
app.kubernetes.io/managed-by: Helm
{{- end }}
