# Apps (Argo CD app-of-apps)

- **bsx-jobs/** – Kustomize overlay that references the Helm chart at `../../bsx-jobs` (relative).
- **bsx-jobs-application.yaml** – Argo CD `Application` that deploys the overlay.

Set `spec.source.repoURL` in each `*-application.yaml` to your Git repo URL (e.g. the same as `argocd_github_url` in Terraform).
