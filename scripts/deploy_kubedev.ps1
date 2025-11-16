# Deploy KubeDev CRD and controller into the cluster
Write-Host "Applying CRD..."
kubectl apply -f k8s/crd/kubedev_crd.yaml

Write-Host "Applying RBAC..."
kubectl apply -f k8s/controller/rbac.yaml

Write-Host "Applying controller code/config..."
kubectl apply -f k8s/controller/configmap.yaml
kubectl apply -f k8s/controller/deployment.yaml

kubectl -n kubedev-system rollout status deploy/kubedev-controller --timeout=120s

Write-Host "Done. Set optional defaults via k8s/controller/deployment.yaml ConfigMap (ide-domain, default-image)."

