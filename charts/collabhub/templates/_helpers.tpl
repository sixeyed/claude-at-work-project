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

{{/* Resource name for one pool of a component, e.g. collabhub-worker-notify. */}}
{{- define "collabhub.poolFullname" -}}
{{- printf "%s-%s" (include "collabhub.componentFullname" .) .pool | trunc 63 | trimSuffix "-" -}}
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

collabhub.io/pool does the same job one level down: both Worker pools are
component "worker", and without it each pool's Deployment would select the
other's pods. Omit `pool` from the dict to select every pool of a component,
which is what a NetworkPolicy wants.
*/}}
{{- define "collabhub.selectorLabels" -}}
app.kubernetes.io/name: {{ include "collabhub.name" .root }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/component: {{ .name }}
{{- with .pool }}
collabhub.io/pool: {{ . }}
{{- end }}
{{- end -}}

{{/*
NetworkPolicy rules. Each renders one list item for a policy's ingress or
egress, so a policy reads as a list of includes.

External peers come from .Values.networkPolicy.peers and fail the render when
empty: a pod that cannot reach its database is worse than a chart that refuses.
In-release peers are matched on this chart's own labels, with no pool, so one
rule covers every Worker pool.

Ports: ingress names the pod's `http` port; egress to a component uses that
component's numeric port, because a NetworkPolicy is evaluated against the pod
behind a Service, not the Service.
*/}}

{{/* Usage: include "collabhub.ingressFromController" (dict "root" $ "name" "auth") */}}
{{- define "collabhub.ingressFromController" -}}
{{- $peer := .root.Values.networkPolicy.peers.ingressController -}}
{{- if not $peer.from -}}
{{- fail (printf "networkPolicy.peers.ingressController.from is empty, and %s needs it. Set it, or set networkPolicy.enabled=false." .name) -}}
{{- end -}}
- from:
    {{- toYaml $peer.from | nindent 4 }}
  ports:
    - port: http
      protocol: TCP
{{- end -}}

{{/* Usage: include "collabhub.ingressFromComponents" (dict "root" $ "from" (list "worker")) */}}
{{- define "collabhub.ingressFromComponents" -}}
- from:
    {{- range .from }}
    - podSelector:
        matchLabels:
          {{- include "collabhub.selectorLabels" (dict "root" $.root "name" .) | nindent 10 }}
    {{- end }}
  ports:
    - port: http
      protocol: TCP
{{- end -}}

{{/* Usage: include "collabhub.egressToPeer" (dict "root" $ "name" "auth" "peer" "postgres") */}}
{{- define "collabhub.egressToPeer" -}}
{{- $peer := index .root.Values.networkPolicy.peers .peer -}}
{{- if not $peer.to -}}
{{- fail (printf "networkPolicy.peers.%s.to is empty, and %s needs it. Set it, or set networkPolicy.enabled=false." .peer .name) -}}
{{- end -}}
- to:
    {{- toYaml $peer.to | nindent 4 }}
  ports:
    {{- toYaml $peer.ports | nindent 4 }}
{{- end -}}

{{/* Usage: include "collabhub.egressToComponent" (dict "root" $ "target" "auth") */}}
{{- define "collabhub.egressToComponent" -}}
{{- $target := index .root.Values.components .target -}}
- to:
    - podSelector:
        matchLabels:
          {{- include "collabhub.selectorLabels" (dict "root" .root "name" .target) | nindent 10 }}
  ports:
    - port: {{ $target.port }}
      protocol: TCP
{{- end -}}
