{{/*
Expand the chart name.
*/}}
{{- define "chore-tracker.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified application name.
*/}}
{{- define "chore-tracker.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{- define "chore-tracker.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "chore-tracker.labels" -}}
helm.sh/chart: {{ include "chore-tracker.chart" . }}
{{ include "chore-tracker.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "chore-tracker.selectorLabels" -}}
app.kubernetes.io/name: {{ include "chore-tracker.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "chore-tracker.backendSelectorLabels" -}}
{{ include "chore-tracker.selectorLabels" . }}
app.kubernetes.io/component: backend
{{- end }}

{{- define "chore-tracker.backendLabels" -}}
{{ include "chore-tracker.labels" . }}
app.kubernetes.io/component: backend
{{- end }}

{{- define "chore-tracker.frontendSelectorLabels" -}}
{{ include "chore-tracker.selectorLabels" . }}
app.kubernetes.io/component: frontend
{{- end }}

{{- define "chore-tracker.frontendLabels" -}}
{{ include "chore-tracker.labels" . }}
app.kubernetes.io/component: frontend
{{- end }}

{{- define "chore-tracker.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "chore-tracker.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{- define "chore-tracker.dataClaimName" -}}
{{- if .Values.persistence.existingClaim }}
{{- .Values.persistence.existingClaim }}
{{- else }}
{{- printf "%s-data" (include "chore-tracker.fullname" .) }}
{{- end }}
{{- end }}

{{- define "chore-tracker.databasePath" -}}
{{- printf "%s/%s" .Values.persistence.mountPath .Values.persistence.databaseFile }}
{{- end }}

{{/*
The browser-facing origin. Derive it from the ingress host and TLS setting when
it is not explicitly supplied.
*/}}
{{- define "chore-tracker.appOrigin" -}}
{{- if .Values.config.appOrigin }}
{{- .Values.config.appOrigin }}
{{- else if .Values.ingress.enabled }}
{{- $host := required "ingress.host is required when ingress is enabled" .Values.ingress.host }}
{{- printf "%s://%s" (ternary "https" "http" .Values.ingress.tls.enabled) $host }}
{{- else }}
{{- required "config.appOrigin is required when ingress is disabled" .Values.config.appOrigin }}
{{- end }}
{{- end }}

{{- define "chore-tracker.passkeyOrigin" -}}
{{- default (include "chore-tracker.appOrigin" .) .Values.config.passkeyOrigin }}
{{- end }}

{{- define "chore-tracker.passkeyRpId" -}}
{{- if .Values.config.passkeyRpId }}
{{- .Values.config.passkeyRpId }}
{{- else if .Values.ingress.enabled }}
{{- required "ingress.host is required when ingress is enabled" .Values.ingress.host }}
{{- else }}
{{- required "config.passkeyRpId is required when ingress is disabled" .Values.config.passkeyRpId }}
{{- end }}
{{- end }}
