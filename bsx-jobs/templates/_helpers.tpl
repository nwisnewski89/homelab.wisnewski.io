{{/*
Expand app name and create a DNS-safe job name (max 63 chars).
*/}}
{{- define "bsx-jobs.jobName" -}}
{{- $name := index .job "job-name" | default "job" -}}
{{- $suffix := randAlphaNum 5 | lower -}}
{{- printf "%s-%s" $name $suffix | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Full image reference for a job (with optional overrides).
imageOverride replaces repo/image; imageTagOverride replaces tag.
*/}}
{{- define "bsx-jobs.image" -}}
{{- $base := index .job "image-override" | default (printf "%s/%s" (.root.Values.repo | default "docker.io/library") (.root.Values.image | default "busybox")) -}}
{{- $tag := index .job "image-tag-override" | default (.root.Values.tag | default "latest") -}}
{{- printf "%s:%s" $base $tag -}}
{{- end -}}
