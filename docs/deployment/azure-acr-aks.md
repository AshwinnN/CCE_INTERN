# Build in Azure Container Registry and deploy to AKS

This project has separate Compose files for local container use:

- `docker-compose.backend.yaml`: PostgreSQL and the CCE backend.
- `docker-compose.frontend.yaml`: the static React frontend served by Nginx.

They are not required to build images in Azure. ACR Tasks builds and pushes the
images remotely, so Docker does not need to be installed on your workstation.

## Prerequisites

Install the Azure CLI and `kubectl`, then sign in. Your Azure identity needs
permission to queue ACR builds and to deploy to the AKS cluster.

```powershell
az login
az account set --subscription "<subscription-id-or-name>"

$resourceGroup = "<resource-group>"
$registry = "<acr-name-without-azurecr-io>"
$aks = "<aks-cluster-name>"
$tag = "2026.09.10.1"
$loginServer = az acr show --name $registry --resource-group $resourceGroup --query loginServer --output tsv
```

## Give AKS permission to pull images

For an AKS cluster and ACR in the same Microsoft Entra tenant, attach the ACR
to the cluster once. This grants the kubelet identity image-pull access.

```powershell
az aks update --resource-group $resourceGroup --name $aks --attach-acr $registry
az aks get-credentials --resource-group $resourceGroup --name $aks --overwrite-existing
```

For an ABAC-enabled registry, use the appropriate repository-reader role
instead of `AcrPull`; do not enable the ACR admin user for this deployment.

## Build and push without Docker

Run these commands from the repository root. Each command uploads the source
context to ACR Tasks, builds there, and pushes the completed image.

```powershell
az acr build --registry $registry --image "cce/frontend:$tag" --file deploy/docker/Dockerfile.frontend --timeout 1800 .
```

The backend installs the private `agenticplane` package. Set the private index
URL only in your shell or CI secret store, never in a tracked `.env` file.
The Dockerfile consumes it during the dependency-install step only; ACR's
`--secret-build-arg` keeps the value out of ACR build logs.

```powershell
$env:PIP_EXTRA_INDEX_URL = "<private-python-index-url-containing-credential>"
az acr build --registry $registry --image "cce/backend:$tag" --file deploy/docker/Dockerfile.backend --timeout 1800 --secret-build-arg "PIP_EXTRA_INDEX_URL=$env:PIP_EXTRA_INDEX_URL" .
Remove-Item Env:PIP_EXTRA_INDEX_URL
```

Confirm both images are present:

```powershell
az acr repository show-tags --name $registry --repository cce/backend --output table
az acr repository show-tags --name $registry --repository cce/frontend --output table
```

## Create runtime configuration in AKS

Create a non-committed production environment file, for example
`backend.production.env`. It must contain production values, especially a
managed PostgreSQL connection string, LLM credentials, and (when used) the
AgenticPlane endpoint/key. Do not reuse the local `localhost` database URL.

```powershell
kubectl create namespace cce --dry-run=client -o yaml | kubectl apply -f -
kubectl create secret generic cce-backend-env --namespace cce --from-env-file=backend.production.env --dry-run=client -o yaml | kubectl apply -f -
```

Create the backend deployment and internal Service:

```powershell
kubectl --namespace cce create deployment cce-backend --image="$loginServer/cce/backend:$tag" --port=8080
kubectl --namespace cce set env deployment/cce-backend --from=secret/cce-backend-env
kubectl --namespace cce set env deployment/cce-backend CCE_HTTP_PORT=8080 CCE_GRPC_HOST=0.0.0.0
kubectl --namespace cce expose deployment cce-backend --name=cce-backend --port=8080 --target-port=8080
```

Create the frontend deployment and public Service. The Nginx frontend proxies
`/api` to the internal backend Service, so no browser CORS configuration is
needed.

```powershell
kubectl --namespace cce create deployment cce-frontend --image="$loginServer/cce/frontend:$tag" --port=80
kubectl --namespace cce set env deployment/cce-frontend BACKEND_UPSTREAM=cce-backend:8080
kubectl --namespace cce expose deployment cce-frontend --name=cce-frontend --type=LoadBalancer --port=80 --target-port=80
kubectl --namespace cce rollout status deployment/cce-backend
kubectl --namespace cce rollout status deployment/cce-frontend
kubectl --namespace cce get service cce-frontend
```

Use the external IP from the final command. For production, replace the public
LoadBalancer with your approved ingress controller, hostname, and TLS policy.

## Update a release

Build a new immutable tag, then update both deployments and wait for rollout:

```powershell
kubectl --namespace cce set image deployment/cce-backend cce-backend="$loginServer/cce/backend:<new-tag>"
kubectl --namespace cce set image deployment/cce-frontend cce-frontend="$loginServer/cce/frontend:<new-tag>"
kubectl --namespace cce rollout status deployment/cce-backend
kubectl --namespace cce rollout status deployment/cce-frontend
```

Do not use `latest` for releases. Pin the tag that was built and tested.
