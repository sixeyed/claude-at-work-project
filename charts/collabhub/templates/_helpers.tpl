{{/*
Helpers take a dict of {root, name} rather than the usual bare context, because
every resource in this chart belongs to one of the components under
.Values.components and needs that component's name in its labels.

Usage: {{ include "collabhub.labels" (dict "root" $ "name" $name) }}
*/}}

{{- define "collabhub.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "collabhub.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/* Resource name for one component, e.g. collabhub-auth. Truncated to 63. */}}
{{- define "collabhub.componentFullname" -}}
{{- printf "%s-%s" (include "collabhub.fullname" .root) .name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "collabhub.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .root.Chart.Name .root.Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{ include "collabhub.selectorLabels" . }}
app.kubernetes.io/version: {{ .root.Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .root.Release.Service }}
{{- end -}}

{{/*
app.kubernetes.io/component is what keeps one component's Deployment from
selecting another's pods — every component shares the name and instance labels.
*/}}
{{- define "collabhub.selectorLabels" -}}
app.kubernetes.io/name: {{ include "collabhub.name" .root }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/component: {{ .name }}
{{- end -}}
