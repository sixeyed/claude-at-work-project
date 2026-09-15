{{/*
Helpers take a dict of {root, name}: every resource here belongs to one
dependency and carries that dependency's name in its labels.

Resources are named plainly — `postgres`, `redis-cache`, `dex` — rather than
prefixed with the release, so in-cluster addresses read exactly like the
Compose service names in .env.example.
*/}}

{{- define "collabhub-local.labels" -}}
{{ include "collabhub-local.selectorLabels" . }}
app.kubernetes.io/part-of: collabhub-local
app.kubernetes.io/managed-by: {{ .root.Release.Service }}
{{- end -}}

{{- define "collabhub-local.selectorLabels" -}}
app.kubernetes.io/name: {{ .name }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
{{- end -}}

{{/* A service's database DSN. Usage: include "collabhub-local.dsn" (dict "root" $ "db" "auth") */}}
{{- define "collabhub-local.dsn" -}}
{{- $pg := .root.Values.postgres -}}
{{- printf "postgresql+asyncpg://%s:%s@postgres:5432/collabhub_%s" $pg.user $pg.password .db -}}
{{- end -}}
