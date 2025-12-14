"""
Kubernetes Service
K8s 클러스터와의 상호작용을 관리하는 서비스
"""

import asyncio
from datetime import datetime
import structlog
from typing import Dict, List, Any, Optional
from kubernetes import client, config
from kubernetes.client.rest import ApiException

log = structlog.get_logger(__name__)


class KubernetesService:
    """Kubernetes 클러스터 관리 서비스"""

    def __init__(self):
        """K8s 클라이언트 초기화"""
        try:
            try:
                config.load_kube_config()
                log.info("Loaded kubeconfig for development")
            except Exception:
                config.load_incluster_config()
                log.info("Loaded in-cluster config")

            # For development: disable SSL verification; optional proxy override
            from kubernetes import client
            import os
            conf = client.Configuration.get_default_copy()
            conf.verify_ssl = False

            proxy_host = os.getenv("KUBEDEV_PROXY_HOST")
            if proxy_host:
                conf.host = proxy_host
                log.info("Kubernetes API server address overridden", host=conf.host)
            else:
                log.info("Using default Kubernetes API server address from kubeconfig/in-cluster")

            client.Configuration.set_default(conf)
            log.info("SSL certificate verification disabled for Kubernetes client.")

            self.k8s_available = True
            self.v1 = client.CoreV1Api()
            self.apps_v1 = client.AppsV1Api()
            self.networking_v1 = client.NetworkingV1Api()
            self.custom_api = client.CustomObjectsApi()
            log.info("Kubernetes clients initialized successfully")
        except Exception as e:
            log.warning("Kubernetes config not available. Some features may not work.", error=str(e))
            self.k8s_available = False

    async def create_custom_object(self, custom_object: Dict[str, Any]) -> Dict[str, Any]:
        """KubeDevEnvironment CRD와 같은 사용자 정의 리소스를 생성합니다."""
        self._check_k8s_availability()

        api_version = custom_object.get("apiVersion")
        if not api_version or "/" not in api_version:
            raise ValueError("Invalid apiVersion in custom object")
            
        group, version = api_version.split('/')
        kind = custom_object.get("kind")
        namespace = custom_object.get("metadata", {}).get("namespace", "default")
        
        # CRD의 정확한 plural form을 사용해야 합니다. 'kubedevenvironments'
        plural = "kubedevenvironments" if kind == "KubeDevEnvironment" else f"{kind.lower()}s"

        log.info(
            "Attempting to create custom object",
            group=group,
            version=version,
            namespace=namespace,
            plural=plural,
            name=custom_object.get("metadata", {}).get("name")
        )

        try:
            api_response = self.custom_api.create_namespaced_custom_object(
                group=group,
                version=version,
                namespace=namespace,
                plural=plural,
                body=custom_object,
            )
            log.info("Custom object created successfully")
            return api_response
        except ApiException as e:
            log.error("Failed to create custom object", error=str(e), exc_info=True)
            # 에러 메시지를 더 유용하게 만듭니다.
            error_body = e.body
            if hasattr(e, 'body'):
                try:
                    import json
                    error_details = json.loads(e.body)
                    error_body = error_details.get("message", e.body)
                except (json.JSONDecodeError, AttributeError):
                    pass # 파싱 실패 시 원본 body 사용
            raise Exception(f"Failed to create custom object: {error_body}")

    def _check_k8s_availability(self):
        """K8s 연결 상태 확인"""
        if not self.k8s_available:
            raise Exception("Kubernetes cluster is not available. Please check your kubeconfig.")

    async def create_namespace(self, namespace: str) -> bool:
        """네임스페이스 생성"""
        self._check_k8s_availability()
        log.info("Creating namespace", namespace=namespace)
        try:
            namespace_manifest = client.V1Namespace(
                metadata=client.V1ObjectMeta(name=namespace, labels={"kubdev.managed": "true"})
            )
            self.v1.create_namespace(namespace_manifest)
            log.info("Namespace created successfully", namespace=namespace)
            return True
        except ApiException as e:
            if e.status == 409:  # Already exists
                log.info("Namespace already exists", namespace=namespace)
                return True
            log.error("Failed to create namespace", namespace=namespace, error=str(e), exc_info=True)
            raise Exception(f"Failed to create namespace: {str(e)}")

    async def create_resource_quota(self, namespace: str, quota_name: str, **kwargs) -> bool:
        """리소스 쿼터 생성"""
        self._check_k8s_availability()
        log.info("Creating resource quota", namespace=namespace, name=quota_name, spec=kwargs)
        try:
            quota_manifest = client.V1ResourceQuota(
                metadata=client.V1ObjectMeta(name=quota_name, namespace=namespace),
                spec=client.V1ResourceQuotaSpec(hard=kwargs)
            )
            self.v1.create_namespaced_resource_quota(namespace, quota_manifest)
            log.info("Resource quota created successfully", namespace=namespace, name=quota_name)
            return True
        except ApiException as e:
            if e.status == 409:
                log.info("Resource quota already exists", namespace=namespace, name=quota_name)
                return True
            log.error("Failed to create resource quota", namespace=namespace, name=quota_name, error=str(e), exc_info=True)
            raise Exception(f"Failed to create resource quota: {str(e)}")

    async def create_deployment(self, namespace: str, deployment_name: str, image: str, **kwargs) -> bool:
        """디플로이먼트 생성"""
        self._check_k8s_availability()
        log.info("Creating deployment", namespace=namespace, name=deployment_name, image=image)
        try:
            env_vars = [client.V1EnvVar(name=k, value=str(v)) for k, v in kwargs.get("environment_vars", {}).items()]
            container = client.V1Container(
                name="dev-environment",
                image=image,
                ports=[client.V1ContainerPort(container_port=8080)],
                env=env_vars,
                resources=client.V1ResourceRequirements(
                    limits=kwargs.get("resource_limits", {})
                )
            )
            template = client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(labels={"app": deployment_name, "kubdev.managed": "true"}),
                spec=client.V1PodSpec(containers=[container])
            )
            deployment = client.V1Deployment(
                metadata=client.V1ObjectMeta(name=deployment_name, namespace=namespace, labels={"kubdev.managed": "true"}),
                spec=client.V1DeploymentSpec(
                    replicas=1,
                    selector=client.V1LabelSelector(match_labels={"app": deployment_name}),
                    template=template
                )
            )
            self.apps_v1.create_namespaced_deployment(namespace, deployment)
            log.info("Deployment created successfully", namespace=namespace, name=deployment_name)
            return True
        except ApiException as e:
            log.error("Failed to create deployment", namespace=namespace, name=deployment_name, error=str(e), exc_info=True)
            raise Exception(f"Failed to create deployment: {str(e)}")

    async def create_service(self, namespace: str, service_name: str, deployment_name: str, port: int = 8080) -> bool:
        """서비스 생성"""
        self._check_k8s_availability()
        log.info("Creating service", namespace=namespace, name=service_name)
        try:
            service = client.V1Service(
                metadata=client.V1ObjectMeta(name=service_name, namespace=namespace, labels={"kubdev.managed": "true"}),
                spec=client.V1ServiceSpec(
                    selector={"app": deployment_name},
                    ports=[client.V1ServicePort(port=port, target_port=8080)],
                    type="ClusterIP"
                )
            )
            self.v1.create_namespaced_service(namespace, service)
            log.info("Service created successfully", namespace=namespace, name=service_name)
            return True
        except ApiException as e:
            log.error("Failed to create service", namespace=namespace, name=service_name, error=str(e), exc_info=True)
            raise Exception(f"Failed to create service: {str(e)}")

    async def create_ingress(self, namespace: str, ingress_name: str, service_name: str, host: str, service_port: int = 8080) -> bool:
        """인그레스 생성"""
        self._check_k8s_availability()
        log.info("Creating ingress", namespace=namespace, name=ingress_name, host=host)
        try:
            path = client.V1HTTPIngressPath(
                path="/",
                path_type="Prefix",
                backend=client.V1IngressBackend(
                    service=client.V1IngressServiceBackend(name=service_name, port=client.V1ServiceBackendPort(number=service_port))
                )
            )
            rule = client.V1IngressRule(host=host, http=client.V1HTTPIngressRuleValue(paths=[path]))
            ingress = client.V1Ingress(
                metadata=client.V1ObjectMeta(
                    name=ingress_name,
                    namespace=namespace,
                    labels={"kubdev.managed": "true"},
                    annotations={
                        "kubernetes.io/ingress.class": "nginx",
                        "nginx.ingress.kubernetes.io/rewrite-target": "/"
                    }
                ),
                spec=client.V1IngressSpec(rules=[rule])
            )
            self.networking_v1.create_namespaced_ingress(namespace, ingress)
            log.info("Ingress created successfully", namespace=namespace, name=ingress_name)
            return True
        except ApiException as e:
            log.error("Failed to create ingress", namespace=namespace, name=ingress_name, error=str(e), exc_info=True)
            raise Exception(f"Failed to create ingress: {str(e)}")

    async def delete_deployment(self, namespace: str, deployment_name: str) -> bool:
        """디플로이먼트 삭제"""
        self._check_k8s_availability()
        log.info("Deleting deployment", namespace=namespace, name=deployment_name)
        try:
            self.apps_v1.delete_namespaced_deployment(deployment_name, namespace)
            log.info("Deployment deleted successfully", namespace=namespace, name=deployment_name)
            return True
        except ApiException as e:
            if e.status == 404:
                log.warning("Deployment not found for deletion", namespace=namespace, name=deployment_name)
                return True
            log.error("Failed to delete deployment", namespace=namespace, name=deployment_name, error=str(e), exc_info=True)
            raise Exception(f"Failed to delete deployment: {str(e)}")

    async def delete_service(self, namespace: str, service_name: str) -> bool:
        """서비스 삭제"""
        self._check_k8s_availability()
        log.info("Deleting service", namespace=namespace, name=service_name)
        try:
            self.v1.delete_namespaced_service(service_name, namespace)
            log.info("Service deleted successfully", namespace=namespace, name=service_name)
            return True
        except ApiException as e:
            if e.status == 404:
                log.warning("Service not found for deletion", namespace=namespace, name=service_name)
                return True
            log.error("Failed to delete service", namespace=namespace, name=service_name, error=str(e), exc_info=True)
            raise Exception(f"Failed to delete service: {str(e)}")

    async def get_deployment_status(self, namespace: str, deployment_name: str) -> Dict[str, Any]:
        """디플로이먼트 상태 조회"""
        try:
            self._check_k8s_availability()
        except Exception as e:
            log.warning("Kubernetes unavailable, returning mock deployment status", namespace=namespace, name=deployment_name, error=str(e))
            return {"name": deployment_name, "namespace": namespace, "status": "Error", "ready_replicas": 0, "total_replicas": 0, "error": str(e)}

        log.info("Getting deployment status", namespace=namespace, name=deployment_name)
        try:
            deployment = self.apps_v1.read_namespaced_deployment(deployment_name, namespace)
            status = {
                "name": deployment.metadata.name,
                "namespace": deployment.metadata.namespace,
                "status": "Running" if deployment.status.ready_replicas else "Pending",
                "ready_replicas": deployment.status.ready_replicas or 0,
                "total_replicas": deployment.status.replicas or 0,
            }
            log.info("Deployment status retrieved", **status)
            return status
        except ApiException as e:
            log.error("Failed to get deployment status", namespace=namespace, name=deployment_name, error=str(e))
            return {"name": deployment_name, "namespace": namespace, "status": "Error", "ready_replicas": 0, "total_replicas": 0, "error": str(e)}
        except Exception as e:
            log.error("Unexpected error getting deployment status", namespace=namespace, name=deployment_name, error=str(e), exc_info=True)
            return {"name": deployment_name, "namespace": namespace, "status": "Error", "ready_replicas": 0, "total_replicas": 0, "error": str(e)}

    async def get_pod_logs(self, namespace: str, deployment_name: str, tail_lines: int = 100) -> List[str]:
        """파드 로그 조회"""
        try:
            self._check_k8s_availability()
        except Exception as e:
            log.warning("Kubernetes unavailable, returning log placeholder", namespace=namespace, deployment=deployment_name, error=str(e))
            return [f"Kubernetes unavailable: {str(e)}"]
        log.info("Getting pod logs", namespace=namespace, deployment=deployment_name, lines=tail_lines)
        try:
            pods = self.v1.list_namespaced_pod(namespace=namespace, label_selector=f"app={deployment_name}")
            if not pods.items:
                log.warning("No pods found for deployment", namespace=namespace, deployment=deployment_name)
                return [f"No pods found for deployment: {deployment_name}"]
            pod = pods.items[0]
            logs = self.v1.read_namespaced_pod_log(name=pod.metadata.name, namespace=namespace, tail_lines=tail_lines)
            log.info("Pod logs retrieved successfully", namespace=namespace, pod=pod.metadata.name)
            return logs.split('\n') if logs else []
        except ApiException as e:
            log.error("Failed to get pod logs", namespace=namespace, deployment=deployment_name, error=str(e), exc_info=True)
            return [f"Error getting logs: {str(e)}"]

    async def get_cluster_overview(self) -> Dict[str, Any]:
        """클러스터 전체 현황 조회"""
        try:
            self._check_k8s_availability()
        except Exception as e:
            log.warning("Kubernetes unavailable, returning mock cluster overview", error=str(e))
            return {"cluster_info": {"total_nodes": 3, "ready_nodes": 2, "total_pods": 12}, "mock": True}

        log.info("Getting cluster overview")
        try:
            nodes = self.v1.list_node()
            pods = self.v1.list_pod_for_all_namespaces()
            ready_nodes = sum(1 for n in nodes.items for c in n.status.conditions if c.type == "Ready" and c.status == "True")
            overview = {
                "total_nodes": len(nodes.items),
                "ready_nodes": ready_nodes,
                "total_pods": len(pods.items),
            }
            log.info("Cluster overview retrieved", **overview)
            return {"cluster_info": overview}
        except ApiException as e:
            log.error("Failed to get cluster overview", error=str(e), exc_info=True)
            raise Exception(f"Failed to get cluster overview: {str(e)}")
        except Exception as e:
            # Fallback mock data when cluster not reachable
            log.warning("Cluster overview fallback to mock", error=str(e))
            return {"cluster_info": {"total_nodes": 3, "ready_nodes": 2, "total_pods": 12}, "mock": True}

    async def get_all_environments_status(self) -> List[Dict[str, Any]]:
        """모든 KubeDev 환경 상태 조회"""
        try:
            self._check_k8s_availability()
        except Exception as e:
            log.warning("Kubernetes unavailable, returning mock environments", error=str(e))
            return [
                {"namespace": "mock-ns-1", "deployment": "mock-dep-a", "status": "Running"},
                {"namespace": "mock-ns-2", "deployment": "mock-dep-b", "status": "Pending"},
            ]
        log.info("Getting status for all environments")
        try:
            deployments = self.apps_v1.list_deployment_for_all_namespaces(label_selector="kubdev.managed=true")
            environments = [
                {
                    "namespace": dep.metadata.namespace,
                    "deployment": dep.metadata.name,
                    "status": "Running" if dep.status.ready_replicas else "Pending",
                }
                for dep in deployments.items
            ]
            log.info("Retrieved status for all environments", count=len(environments))
            return environments
        except ApiException as e:
            log.error("Failed to get all environments status", error=str(e), exc_info=True)
            return []
        except Exception as e:
            log.warning("Fallback environments status mock", error=str(e), exc_info=True)
            return [
                {"namespace": "mock-ns-1", "deployment": "mock-dep-a", "status": "Running"},
                {"namespace": "mock-ns-2", "deployment": "mock-dep-b", "status": "Pending"},
            ]

    async def get_live_resource_metrics(self, namespace: str) -> Dict[str, Any]:
        """실시간 리소스 메트릭 조회 (메트릭 서버 필요)"""
        try:
            self._check_k8s_availability()
        except Exception as e:
            log.warning("Kubernetes unavailable, returning empty metrics", error=str(e), namespace=namespace)
            return {"namespace": namespace, "pods": [], "error": "k8s_unavailable"}
        log.info("Getting live resource metrics", namespace=namespace)

        try:
            # 해당 네임스페이스의 Pod들 조회
            pods = self.v1.list_namespaced_pod(namespace=namespace)

            metrics_data = {
                "namespace": namespace,
                "pods": []
            }

            for pod in pods.items:
                pod_metrics = {
                    "name": pod.metadata.name,
                    "status": pod.status.phase,
                    "cpu_usage_millicores": 0,  # 메트릭 서버 없이는 추정값
                    "memory_usage_mb": 0,       # 메트릭 서버 없이는 추정값
                    "ready": any(condition.status == "True" for condition in pod.status.conditions if condition.type == "Ready") if pod.status.conditions else False
                }
                metrics_data["pods"].append(pod_metrics)

            log.info("Retrieved live metrics for namespace", namespace=namespace, pod_count=len(metrics_data["pods"]))
            return metrics_data

        except ApiException as e:
            log.error("Failed to get live metrics", namespace=namespace, error=str(e), exc_info=True)
            return {
                "namespace": namespace,
                "error": str(e),
                "pods": []
            }

    async def get_resource_quota_status(self, namespace: str, quota_name: str) -> Dict[str, Any]:
        """리소스 쿼터 상태 조회"""
        try:
            self._check_k8s_availability()
        except Exception as e:
            log.warning("Kubernetes unavailable, returning quota unavailable", error=str(e), namespace=namespace, quota_name=quota_name)
            return {"status": "unavailable", "error": str(e)}
        log.info("Getting resource quota status", namespace=namespace, quota_name=quota_name)

        try:
            quota = self.v1.read_namespaced_resource_quota(quota_name, namespace)
            hard = quota.status.hard or {}
            used = quota.status.used or {}

            def pct(resource):
                if resource in hard and resource in used:
                    try:
                        return round((float(used[resource].strip('Mi').strip('Gi')) /
                                      float(hard[resource].strip('Mi').strip('Gi'))) * 100, 2)
                    except Exception:
                        return None
                return None

            return {
                "status": "available",
                "hard": hard,
                "used": used,
                "utilization": {
                    "cpu_percent": pct("cpu"),
                    "memory_percent": pct("memory")
                }
            }
        except ApiException as e:
            if e.status == 404:
                return {"status": "not_found"}
            log.error("Failed to get resource quota status", namespace=namespace, quota_name=quota_name, error=str(e), exc_info=True)
            raise

    async def scale_deployment(self, namespace: str, deployment_name: str, replicas: int) -> bool:
        """Deployment 스케일 조정"""
        try:
            self._check_k8s_availability()
        except Exception as e:
            log.warning("Kubernetes unavailable, cannot scale deployment", namespace=namespace, deployment=deployment_name, replicas=replicas, error=str(e))
            return False

        log.info("Scaling deployment", namespace=namespace, deployment=deployment_name, replicas=replicas)

        try:
            # 현재 Deployment 조회
            deployment = self.apps_v1.read_namespaced_deployment(
                name=deployment_name,
                namespace=namespace
            )

            # 레플리카 수 변경
            deployment.spec.replicas = replicas

            # Deployment 업데이트
            self.apps_v1.patch_namespaced_deployment(
                name=deployment_name,
                namespace=namespace,
                body=deployment
            )

            log.info("Deployment scaled successfully", namespace=namespace, deployment=deployment_name, replicas=replicas)
            return True

        except ApiException as e:
            log.error("Failed to scale deployment", namespace=namespace, deployment=deployment_name, replicas=replicas, error=str(e), exc_info=True)
            return False
        except Exception as e:
            log.error("Unexpected error scaling deployment", namespace=namespace, deployment=deployment_name, replicas=replicas, error=str(e), exc_info=True)
            return False

    async def delete_namespace(self, namespace: str) -> bool:
        """네임스페이스 및 모든 리소스 삭제"""
        self._check_k8s_availability()
        log.info("Deleting namespace and all resources", namespace=namespace)

        try:
            # 네임스페이스 삭제 (모든 리소스가 함께 삭제됨)
            self.v1.delete_namespace(name=namespace)
            log.info("Namespace deleted successfully", namespace=namespace)
            return True

        except ApiException as e:
            if e.status == 404:
                log.info("Namespace already deleted", namespace=namespace)
                return True
            log.error("Failed to delete namespace", namespace=namespace, error=str(e), exc_info=True)
            return False

    async def create_custom_object(self, custom_object: Dict[str, Any]) -> Dict[str, Any]:
        """KubeDevEnvironment와 같은 커스텀 리소스를 생성합니다."""
        self._check_k8s_availability()

        api_version = custom_object.get("apiVersion")
        kind = custom_object.get("kind")
        metadata = custom_object.get("metadata", {})
        namespace = metadata.get("namespace", "default")
        name = metadata.get("name")

        log.info("Creating custom object", kind=kind, name=name, namespace=namespace)

        if not all([api_version, kind, name]):
            raise ValueError("Custom object must have apiVersion, kind, and metadata.name")

        try:
            group, version = api_version.split('/')

            # 프로젝트의 CRD kind가 "KubeDevEnvironment"이므로, 복수형은 "kubedevenvironments" 입니다.
            if kind == "KubeDevEnvironment":
                plural = "kubedevenvironments"
            else:
                # 다른 종류의 CRD를 위한 간단한 복수형 추론 규칙
                plural = f"{kind.lower()}s"

            api_response = self.custom_api.create_namespaced_custom_object(
                group=group,
                version=version,
                namespace=namespace,
                plural=plural,
                body=custom_object,
            )
            log.info("Custom object created successfully", kind=kind, name=name)
            return api_response
        except ApiException as e:
            # e.body는 bytes 타입일 수 있으므로, 안전하게 디코딩하여 실제 에러 메시지를 확인합니다.
            error_body = e.body
            if isinstance(error_body, bytes):
                try:
                    error_body = error_body.decode('utf-8')
                except UnicodeDecodeError:
                    error_body = error_body.decode('cp949', errors='ignore')

            log.error("Failed to create custom object", kind=kind, name=name, error=error_body, exc_info=True)
            raise Exception(f"Failed to create custom object: {error_body}")
        except Exception as e:
            log.error("An unexpected error occurred while creating custom object", kind=kind, name=name, error=str(e), exc_info=True)
            raise e

    async def get_custom_object(self, group: str, version: str, namespace: str, plural: str, name: str) -> Dict[str, Any]:
        """KubeDevEnvironment CRD의 현재 상태를 조회합니다."""
        self._check_k8s_availability()

        log.info("Getting custom object", group=group, version=version, namespace=namespace, plural=plural, name=name)

        try:
            api_response = self.custom_api.get_namespaced_custom_object(
                group=group,
                version=version,
                namespace=namespace,
                plural=plural,
                name=name
            )
            log.info("Custom object retrieved successfully", name=name)
            return api_response
        except ApiException as e:
            error_body = e.body
            if isinstance(error_body, bytes):
                try:
                    error_body = error_body.decode('utf-8')
                except UnicodeDecodeError:
                    error_body = error_body.decode('cp949', errors='ignore')

            log.error("Failed to get custom object", name=name, error=error_body, exc_info=True)
            raise Exception(f"Failed to get custom object: {error_body}")
        except Exception as e:
            log.error("An unexpected error occurred while getting custom object", name=name, error=str(e), exc_info=True)
            raise e

    async def get_nodeport_url(self, service_name: str, namespace: str) -> str:
        """Get service URL for both NodePort and ClusterIP services (with port-forwarding)"""
        self._check_k8s_availability()
        try:
            # Get service to extract port information
            service = self.v1.read_namespaced_service(service_name, namespace)

            # Get first port
            if not service.spec.ports or len(service.spec.ports) == 0:
                log.warning("Service has no ports", service=service_name, namespace=namespace)
                return None

            # Handle based on service type
            if service.spec.type == "NodePort":
                # For NodePort, use the NodePort number
                node_port = service.spec.ports[0].node_port
                url = f"http://localhost:{node_port}"
                log.info("Generated NodePort URL", service=service_name, namespace=namespace, url=url, node_port=node_port)
                return url
            else:
                # For ClusterIP services on Minikube, use minikube service to get the URL
                log.info("ClusterIP service found - attempting minikube service URL", service=service_name, namespace=namespace, service_type=service.spec.type)
                try:
                    import subprocess
                    # Get minikube service URL
                    cmd = ["minikube", "service", service_name, "-n", namespace, "--url"]
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

                    if result.returncode == 0 and result.stdout.strip():
                        url = result.stdout.strip().split('\n')[0]  # Get first URL if multiple
                        log.info("Got minikube service URL", service=service_name, namespace=namespace, url=url)
                        return url
                    else:
                        log.warning("Failed to get minikube service URL", service=service_name, namespace=namespace,
                                  stderr=result.stderr, returncode=result.returncode)
                        return None
                except Exception as e:
                    log.warning("Failed to execute minikube service command", service=service_name, namespace=namespace, error=str(e))
                    return None

        except ApiException as e:
            log.warning("Failed to get service URL", service=service_name, namespace=namespace, error=str(e))
            return None
        except Exception as e:
            log.warning("Unexpected error getting service URL", service=service_name, namespace=namespace, error=str(e))
            return None

    def _cpu_to_millicores(self, raw: Optional[str]) -> Optional[int]:
        """Convert CPU quantity to millicores"""
        if not raw:
            return None
        try:
            if raw.endswith("m"):
                return int(raw[:-1])
            return int(float(raw) * 1000)
        except Exception:
            return None

    def _memory_to_mb(self, raw: Optional[str]) -> Optional[float]:
        """Convert memory quantity to MB"""
        if not raw:
            return None
        try:
            value = raw.lower()
            if value.endswith("ki"):
                return round(float(value[:-2]) / 1024, 2)
            if value.endswith("mi"):
                return float(value[:-2])
            if value.endswith("gi"):
                return float(value[:-2]) * 1024
            if value.endswith("ti"):
                return float(value[:-2]) * 1024 * 1024
            return float(value) / (1024 * 1024)
        except Exception:
            return None

    async def list_managed_pods(self, label_selector: str = "kubdev.managed=true") -> List[Dict[str, Any]]:
        """List pods managed by the platform across namespaces"""
        try:
            self._check_k8s_availability()
        except Exception as e:
            log.warning("Kubernetes unavailable, returning mock pods", error=str(e))
            return [
                {
                    "namespace": "mock-ns-1",
                    "name": "mock-pod-a",
                    "phase": "Running",
                    "ready": True,
                    "restarts": 0,
                    "host_ip": "10.0.0.1",
                    "pod_ip": "10.10.0.1",
                    "start_time": datetime.utcnow().isoformat(),
                    "containers": ["main"],
                },
                {
                    "namespace": "mock-ns-2",
                    "name": "mock-pod-b",
                    "phase": "Pending",
                    "ready": False,
                    "restarts": 1,
                    "host_ip": None,
                    "pod_ip": None,
                    "start_time": None,
                    "containers": ["main"],
                },
            ]

        log.info("Listing managed pods", label_selector=label_selector)

        try:
            pods = self.v1.list_pod_for_all_namespaces(label_selector=label_selector)
            pod_list = []
            for pod in pods.items:
                container_statuses = pod.status.container_statuses or []
                restart_count = sum(cs.restart_count or 0 for cs in container_statuses)
                ready = all(cs.ready for cs in container_statuses) if container_statuses else False

                pod_list.append({
                    "namespace": pod.metadata.namespace,
                    "name": pod.metadata.name,
                    "phase": pod.status.phase,
                    "ready": ready,
                    "restarts": restart_count,
                    "host_ip": pod.status.host_ip,
                    "pod_ip": pod.status.pod_ip,
                    "start_time": pod.status.start_time.isoformat() if pod.status.start_time else None,
                    "containers": [c.name for c in pod.spec.containers] if pod.spec and pod.spec.containers else [],
                })
            return pod_list
        except ApiException as e:
            log.error("Failed to list managed pods", error=str(e), exc_info=True)
            return []
        except Exception as e:
            log.error("Unexpected error listing managed pods", error=str(e), exc_info=True)
            # Return mock pods
            return [
                {
                    "namespace": "mock-ns-1",
                    "name": "mock-pod-a",
                    "phase": "Running",
                    "ready": True,
                    "restarts": 0,
                    "host_ip": "10.0.0.1",
                    "pod_ip": "10.10.0.1",
                    "start_time": datetime.utcnow().isoformat(),
                    "containers": ["main"],
                },
                {
                    "namespace": "mock-ns-2",
                    "name": "mock-pod-b",
                    "phase": "Pending",
                    "ready": False,
                    "restarts": 1,
                    "host_ip": None,
                    "pod_ip": None,
                    "start_time": None,
                    "containers": ["main"],
                },
            ]

    async def get_pod_metrics_for_namespace(self, namespace: str) -> Dict[str, Dict[str, Any]]:
        """Return pod-level metrics from metrics-server if available"""
        try:
            self._check_k8s_availability()
        except Exception as e:
            log.warning("Kubernetes unavailable, returning empty pod metrics", namespace=namespace, error=str(e))
            return {}
        try:
            metrics = self.custom_api.list_namespaced_custom_object(
                group="metrics.k8s.io",
                version="v1beta1",
                namespace=namespace,
                plural="pods",
            )
        except ApiException as e:
            log.warning("Metrics API not available", namespace=namespace, error=str(e))
            return {}
        except Exception as e:
            log.warning("Unexpected metrics API error", namespace=namespace, error=str(e))
            return {}

        pod_metrics: Dict[str, Dict[str, Any]] = {}
        for item in metrics.get("items", []):
            pod_name = item.get("metadata", {}).get("name")
            total_cpu = 0
            total_mem = 0.0
            for container in item.get("containers", []):
                usage = container.get("usage", {})
                cpu_m = self._cpu_to_millicores(usage.get("cpu"))
                mem_mb = self._memory_to_mb(usage.get("memory"))
                total_cpu += cpu_m or 0
                total_mem += mem_mb or 0.0
            pod_metrics[pod_name] = {
                "cpu_millicores": total_cpu,
                "memory_mb": round(total_mem, 2),
            }
        return pod_metrics

    async def list_namespace_events(self, namespace: str, limit: int = 30) -> List[Dict[str, Any]]:
        """Return recent events for a namespace"""
        try:
            self._check_k8s_availability()
        except Exception as e:
            log.warning("Kubernetes unavailable, returning mock namespace events", namespace=namespace, error=str(e))
            return [
                {
                    "name": "mock-event-1",
                    "reason": "MockReason",
                    "message": "This is a mock event",
                    "type": "Normal",
                    "count": 1,
                    "involved_object": "mock-pod-a",
                    "kind": "Pod",
                    "timestamp": datetime.utcnow().isoformat(),
                }
            ]
        try:
            events = self.v1.list_namespaced_event(namespace=namespace)
        except ApiException as e:
            log.error("Failed to list namespace events", namespace=namespace, error=str(e), exc_info=True)
            return []
        except Exception as e:
            log.warning("Namespace events fallback mock", namespace=namespace, error=str(e))
            return [
                {
                    "name": "mock-event-1",
                    "reason": "MockReason",
                    "message": "This is a mock event",
                    "type": "Normal",
                    "count": 1,
                    "involved_object": "mock-pod-a",
                    "kind": "Pod",
                    "timestamp": datetime.utcnow().isoformat(),
                }
            ]

        event_items = []
        for ev in events.items:
            ts = ev.last_timestamp or ev.event_time or ev.first_timestamp or ev.metadata.creation_timestamp
            event_items.append({
                "name": ev.metadata.name,
                "reason": ev.reason,
                "message": ev.message,
                "type": ev.type,
                "count": ev.count,
                "involved_object": ev.involved_object.name if ev.involved_object else None,
                "kind": ev.involved_object.kind if ev.involved_object else None,
                "timestamp": ts.isoformat() if ts else None,
            })

        event_items = sorted(event_items, key=lambda e: e.get("timestamp") or "", reverse=True)
        return event_items[:limit]

    async def get_recent_events(self, namespaces: Optional[List[str]] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Return recent events across namespaces (filtered)"""
        try:
            self._check_k8s_availability()
        except Exception as e:
            log.warning("Kubernetes unavailable, returning mock cluster events", error=str(e))
            now = datetime.utcnow().isoformat()
            return [
                {
                    "namespace": "mock-ns-1",
                    "name": "mock-event-cluster",
                    "reason": "MockCluster",
                    "message": "Cluster event mock",
                    "type": "Normal",
                    "count": 1,
                    "involved_object": "mock-pod-a",
                    "kind": "Pod",
                    "timestamp": now,
                }
            ]
        try:
            events = self.v1.list_event_for_all_namespaces()
        except ApiException as e:
            log.error("Failed to list cluster events", error=str(e), exc_info=True)
            return []
        except Exception as e:
            log.warning("Cluster events fallback mock", error=str(e))
            now = datetime.utcnow().isoformat()
            return [
                {
                    "namespace": "mock-ns-1",
                    "name": "mock-event-cluster",
                    "reason": "MockCluster",
                    "message": "Cluster event mock",
                    "type": "Normal",
                    "count": 1,
                    "involved_object": "mock-pod-a",
                    "kind": "Pod",
                    "timestamp": now,
                }
            ]

        event_items = []
        for ev in events.items:
            if namespaces and ev.metadata.namespace not in namespaces:
                continue
            ts = ev.last_timestamp or ev.event_time or ev.first_timestamp or ev.metadata.creation_timestamp
            event_items.append({
                "namespace": ev.metadata.namespace,
                "name": ev.metadata.name,
                "reason": ev.reason,
                "message": ev.message,
                "type": ev.type,
                "count": ev.count,
                "involved_object": ev.involved_object.name if ev.involved_object else None,
                "kind": ev.involved_object.kind if ev.involved_object else None,
                "timestamp": ts.isoformat() if ts else None,
            })

        event_items = sorted(event_items, key=lambda e: e.get("timestamp") or "", reverse=True)
        return event_items[:limit]

    async def stream_pod_snapshots(self, label_selector: str = "kubdev.managed=true", interval_seconds: int = 5):
        """Async generator yielding pod snapshots for SSE-style streaming"""
        self._check_k8s_availability()
        while True:
            pods = await self.list_managed_pods(label_selector=label_selector)
            yield {
                "pods": pods,
                "timestamp": datetime.utcnow().isoformat()
            }
            await asyncio.sleep(interval_seconds)
