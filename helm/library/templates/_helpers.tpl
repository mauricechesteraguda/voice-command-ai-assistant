{{- define "platform.labels" -}}
app.kubernetes.io/managed-by: Helm
app.kubernetes.io/part-of: voice-command-platform
{{- end }}
{{- define "platform.podSecurityContext" -}}
runAsNonRoot: true
seccompProfile: { type: RuntimeDefault }
{{- end }}
{{- define "platform.containerSecurityContext" -}}
runAsNonRoot: true
allowPrivilegeEscalation: false
readOnlyRootFilesystem: true
capabilities: { drop: [ALL] }
{{- end }}
