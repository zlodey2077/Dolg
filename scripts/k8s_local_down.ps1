param(
    [string]$Namespace = "dolg",
    [switch]$KeepPvcs
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$K8sDir = Join-Path $RepoRoot "deploy/k8s"

Set-Location $RepoRoot

if ($KeepPvcs) {
    kubectl -n $Namespace delete `
        job/dolg-migrate `
        deploy/postgres deploy/redis deploy/dolg-web deploy/dolg-asgi deploy/dolg-worker deploy/dolg-nginx deploy/prometheus deploy/grafana `
        svc/dolg-web svc/dolg-asgi svc/dolg-nginx svc/prometheus svc/grafana svc/postgres svc/redis `
        configmap/dolg-config configmap/nginx-config configmap/prometheus-config `
        secret/dolg-secret `
        pdb/dolg-web-pdb `
        networkpolicy/default-deny `
        networkpolicy/allow-dns-egress `
        networkpolicy/allow-edge-ingress `
        networkpolicy/allow-edge-to-django `
        networkpolicy/allow-edge-to-asgi `
        networkpolicy/allow-django-to-stateful `
        networkpolicy/allow-stateful-from-django `
        networkpolicy/allow-edge-egress `
        networkpolicy/allow-prometheus-scrape `
        networkpolicy/allow-grafana-to-prometheus `
        --ignore-not-found=true
}
else {
    kubectl delete -k $K8sDir --ignore-not-found=true
}
