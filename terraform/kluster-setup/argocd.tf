resource "kubernetes_namespace" "argocd" {
  metadata {
    name = "argocd"
  }
}

resource "kubectl_manifest" "argocd_cert" {
  yaml_body = <<YAML
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: argocdcd-tls
  namespace: argocd
spec:
  secretName: argocd-tls
  issuerRef:
    name: letsencrypt-dns
    kind: ClusterIssuer
  commonName: argocd.${var.domain}
  dnsNames:
    - argocd.${var.domain}
YAML

  depends_on = [
    helm_release.cert_manager,
    kubernetes_namespace.argocd,
    helm_release.argocd,
    kubectl_manifest.kluster_issuer
  ]
}

resource "kubectl_manifest" "argocd_ingress" {
  yaml_body = <<YAML
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: argo-cd-argocd-server
  namespace: argocd
  annotations:
    cert-manager.io/cluster-issuer: "letsencrypt-dns"
    nginx.ingress.kubernetes.io/backend-protocol: "HTTPS"
    nginx.ingress.kubernetes.io/ssl-passthrough: "true"
    nginx.ingress.kubernetes.io/force-ssl-redirect: "true"
spec:
  tls:
  - hosts:
    - argocd.${var.domain}
    secretName: argocd-tls
  ingressClassName: nginx
  rules:
  - host: argocd.${var.domain}
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: argo-cd-argocd-server
            port:
              number: 443
YAML

  depends_on = [
    helm_release.nginx_ingress,
    kubernetes_namespace.argocd,
    helm_release.argocd,
    kubectl_manifest.argocd_cert
  ]
}

resource "helm_release" "argocd" {
  name             = "argo-cd"
  namespace        = "argocd"
  create_namespace = false
  repository       = "https://argoproj.github.io/argo-helm"
  chart            = "argo-cd"
  version          = "8.0.3"

  values = [
    <<-EOF
      global:
        domain: argocd.${var.domain}
      crds:
        keep: false
      configs:
        secret:
          createSecret: true
        cm:
          configManagementPlugins: |
            - name: argocd-vault-plugin
              generate:
                command: ["argocd-vault-plugin"]
                args: ["generate", "./"]
      repoServer:
        volumes:
        - name: custom-tools
          emptyDir: {}
        volumeMounts:
        - name: custom-tools
          mountPath: /usr/local/bin/argocd-vault-plugin
          subPath: argocd-vault-plugin
        initContainers:
        - name: download-tools
          image: curlimages/curl:8.5.0  # Using a lightweight curl image
          command: [sh, -c]
          args:
            - |
              curl -L -o /custom-tools/argocd-vault-plugin \
                https://github.com/argoproj-labs/argocd-vault-plugin/releases/download/v1.17.0/argocd-vault-plugin_linux_amd64 && \
              chmod +x /custom-tools/argocd-vault-plugin
          volumeMounts:
            - mountPath: /custom-tools
              name: custom-tools
        envFrom:
          - configMapRef:
              name: argocd-vault-plugin-config
    EOF
  ]

  depends_on = [
    kubernetes_namespace.argocd,
    kubectl_manifest.avp_configmap
  ]
}

resource "kubectl_manifest" "avp_configmap" {
  yaml_body = <<YAML
apiVersion: v1
kind: ConfigMap
metadata:
  name: argocd-vault-plugin-config
  namespace: argocd
data:
  AVP_AUTH_TYPE: "k8s"
  AVP_K8S_ROLE: "argocd"
  AVP_TYPE: "vault"
  VAULT_ADDR: "http://vault.vault:8200"
  VAULT_SKIP_VERIFY: "true"
YAML

  depends_on = [
    kubernetes_namespace.argocd,
  ]
}
