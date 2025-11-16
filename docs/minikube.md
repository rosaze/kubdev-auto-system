# Minikube Test Guide (Quick)

- Start cluster:
  - `minikube start --cpus=4 --memory=8g`
- Deploy CRD and controller:
  - `pwsh scripts/deploy_kubedev.ps1`
- Run backend locally (separate shell):
  - `cd backend`
  - `pip install -r requirements.txt`
  - `uvicorn backend.app:app --host 0.0.0.0 --port 8000`
- Create environment via API:
  - `pwsh scripts/demo_create_env.ps1`
- Verify resources:
  - `kubectl get kubedevenvironments -n kubedev-users`
  - `kubectl get ns,po,svc,ing -A -l kubedev.io/owner`
- Port-forward IDE (if no Ingress domain configured):
  - `kubectl -n <workspace-ns> port-forward deploy/ide-<env-name> 8080:8080`
  - open http://localhost:8080
- Cleanup:
  - `kubectl delete kubedevenvironments -n kubedev-users <env-name>`

Notes
- Controller image uses python:3.11-slim and installs kopf at runtime; ensure cluster egress is allowed.
- Set wildcard IDE domain by editing `k8s/controller/deployment.yaml` ConfigMap `ide-domain`.
- Default workspace image can be set via `default-image` (should include code-server).

