"""
Environment Service
개발 환경 생명주기 관리 서비스
"""

import asyncio
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import structlog

from app.models.environment import EnvironmentInstance, EnvironmentStatus
from app.models.project_template import ProjectTemplate
from app.services.kubernetes_service import KubernetesService
from app.core.config import settings


class EnvironmentService:
    """개발 환경 관리 서비스"""

    def __init__(self, db: Session, logger: Optional[structlog.stdlib.BoundLogger] = None):
        self.db = db
        self.k8s_service = KubernetesService()
        self.log = logger or structlog.get_logger(__name__)

    async def deploy_environment(self, environment_id: int) -> Dict[str, Any]:
        """환경을 K8s 클러스터에 배포"""
        log = self.log.bind(environment_id=environment_id)
        log.info("Starting environment deployment")

        environment = self.db.query(EnvironmentInstance).filter(
            EnvironmentInstance.id == environment_id
        ).first()

        if not environment:
            log.error("Deployment failed: environment not found in DB")
            raise Exception("Environment not found")

        template = self.db.query(ProjectTemplate).filter(
            ProjectTemplate.id == environment.template_id
        ).first()

        if not template:
            log.error("Deployment failed: template not found", template_id=environment.template_id)
            raise Exception("Template not found")

        try:
            # 환경 상태 업데이트
            environment.status = EnvironmentStatus.CREATING
            environment.status_message = "Deploying to Kubernetes..."
            self.db.commit()
            log.info("Set environment status to CREATING")

            # 네임스페이스 생성 (없으면)
            await self.k8s_service.create_namespace(environment.k8s_namespace)
            log.info("Namespace ensured", namespace=environment.k8s_namespace)

            # ResourceQuota 생성 (자원 사용량 제한)
            quota_name = f"quota-{environment.k8s_deployment_name}"
            await self.k8s_service.create_resource_quota(
                namespace=environment.k8s_namespace,
                quota_name=quota_name,
                cpu_limit=template.resource_limits.get("cpu", settings.DEFAULT_CPU_LIMIT),
                memory_limit=template.resource_limits.get("memory", settings.DEFAULT_MEMORY_LIMIT),
                storage_limit=template.resource_limits.get("storage", settings.DEFAULT_STORAGE_LIMIT),
                pod_limit=5
            )
            log.info("ResourceQuota created", quota_name=quota_name)

            # 환경변수 준비
            env_vars = {
                "ENVIRONMENT_ID": str(environment.id),
                "TEMPLATE_NAME": template.name,
                "USER_ID": str(environment.user_id),
                **template.environment_variables
            }

            # 리소스 제한 설정
            resource_limits = template.resource_limits or {
                "cpu": settings.DEFAULT_CPU_LIMIT,
                "memory": settings.DEFAULT_MEMORY_LIMIT
            }

            # Deployment 생성
            deployment_result = await self.k8s_service.create_deployment(
                namespace=environment.k8s_namespace,
                deployment_name=environment.k8s_deployment_name,
                image=template.base_image,
                environment_vars=env_vars,
                resource_limits=resource_limits,
                git_repo=environment.git_repository,
                git_branch=environment.git_branch or "main"
            )
            log.info("Deployment created", deployment_name=environment.k8s_deployment_name)

            # Service 생성
            service_result = await self.k8s_service.create_service(
                namespace=environment.k8s_namespace,
                service_name=environment.k8s_service_name,
                deployment_name=environment.k8s_deployment_name,
                port=8080
            )
            log.info("Service created", service_name=environment.k8s_service_name)

            # Ingress 생성 (외부 접속용)
            ingress_host = f"{environment.k8s_deployment_name}.kubdev.local"
            ingress_name = f"ing-{environment.k8s_deployment_name}"

            await self.k8s_service.create_ingress(
                namespace=environment.k8s_namespace,
                ingress_name=ingress_name,
                service_name=environment.k8s_service_name,
                host=ingress_host,
                service_port=8080
            )
            log.info("Ingress created", ingress_name=ingress_name, host=ingress_host)

            # 환경 정보 업데이트
            environment.k8s_ingress_name = ingress_name
            environment.access_url = f"http://{ingress_host}"
            environment.status = EnvironmentStatus.RUNNING
            environment.status_message = "Environment is ready"
            environment.started_at = datetime.utcnow()

            if not environment.expires_at:
                environment.expires_at = datetime.utcnow() + timedelta(hours=settings.ENVIRONMENT_TIMEOUT_HOURS)

            environment.port_mappings = template.exposed_ports or []
            self.db.commit()
            log.info("Environment deployment successful, waiting for ready state")

            asyncio.create_task(self._wait_for_deployment_ready(environment_id))

            return {
                "environment_id": environment.id,
                "status": "deployed",
                "access_url": environment.access_url,
                "deployment": deployment_result,
                "service": service_result
            }

        except Exception as e:
            log.error("Deployment failed with an exception", error=str(e), exc_info=True)
            environment.status = EnvironmentStatus.ERROR
            environment.status_message = f"Deployment failed: {str(e)}"
            self.db.commit()
            raise

    async def _wait_for_deployment_ready(self, environment_id: int, max_wait_time: int = 300):
        """Deployment가 Ready 상태가 될 때까지 대기"""
        log = self.log.bind(environment_id=environment_id)
        log.info("Waiting for deployment to become ready")
        environment = self.db.query(EnvironmentInstance).filter(
            EnvironmentInstance.id == environment_id
        ).first()

        if not environment:
            log.error("Cannot wait for deployment: environment not found")
            return

        start_time = datetime.utcnow()

        while (datetime.utcnow() - start_time).seconds < max_wait_time:
            try:
                status = await self.k8s_service.get_deployment_status(
                    namespace=environment.k8s_namespace,
                    deployment_name=environment.k8s_deployment_name
                )

                if status.get("ready_replicas", 0) >= 1:
                    log.info("Deployment is ready")
                    environment.status = EnvironmentStatus.RUNNING
                    environment.status_message = "Environment is running and ready"
                    self.db.commit()
                    break

                log.info("Deployment not ready yet, waiting...", ready_replicas=status.get("ready_replicas", 0))
                await asyncio.sleep(30)

            except Exception as e:
                log.error("Health check failed while waiting for deployment", error=str(e), exc_info=True)
                environment.status = EnvironmentStatus.ERROR
                environment.status_message = f"Health check failed: {str(e)}"
                self.db.commit()
                break
        else:
            log.warning("Deployment timeout: environment did not become ready")
            environment.status = EnvironmentStatus.ERROR
            environment.status_message = "Deployment timeout - environment did not become ready"
            self.db.commit()

    async def start_environment(self, environment_id: int) -> Dict[str, Any]:
        """환경 시작"""
        log = self.log.bind(environment_id=environment_id)
        log.info("Starting environment")
        environment = self.db.query(EnvironmentInstance).filter(
            EnvironmentInstance.id == environment_id
        ).first()

        if not environment:
            log.error("Start failed: environment not found")
            raise Exception("Environment not found")

        if environment.status == EnvironmentStatus.RUNNING:
            log.warning("Start ignored: environment is already running")
            return {"message": "Environment is already running"}

        try:
            deployment_status = await self.k8s_service.get_deployment_status(
                namespace=environment.k8s_namespace,
                deployment_name=environment.k8s_deployment_name
            )

            if deployment_status.get("status") == "not_found":
                log.info("Deployment not found, creating a new one")
                await self.deploy_environment(environment_id)
            else:
                log.info("Scaling up existing deployment")
                # TODO: Implement scale-up logic in k8s_service
                environment.status = EnvironmentStatus.RUNNING
                environment.started_at = datetime.utcnow()
                environment.last_accessed_at = datetime.utcnow()
                self.db.commit()
            
            log.info("Environment started successfully")
            return {"message": "Environment started successfully"}

        except Exception as e:
            log.error("Failed to start environment", error=str(e), exc_info=True)
            environment.status = EnvironmentStatus.ERROR
            environment.status_message = f"Failed to start: {str(e)}"
            self.db.commit()
            raise

    async def stop_environment(self, environment_id: int) -> Dict[str, Any]:
        """환경 중지"""
        log = self.log.bind(environment_id=environment_id)
        log.info("Stopping environment")
        environment = self.db.query(EnvironmentInstance).filter(
            EnvironmentInstance.id == environment_id
        ).first()

        if not environment:
            log.error("Stop failed: environment not found")
            raise Exception("Environment not found")

        try:
            log.info("Deleting deployment to stop environment", deployment_name=environment.k8s_deployment_name)
            await self.k8s_service.delete_deployment(
                namespace=environment.k8s_namespace,
                deployment_name=environment.k8s_deployment_name
            )

            environment.status = EnvironmentStatus.STOPPED
            environment.stopped_at = datetime.utcnow()
            environment.status_message = "Environment stopped"
            self.db.commit()
            log.info("Environment stopped successfully")
            return {"message": "Environment stopped successfully"}

        except Exception as e:
            log.error("Failed to stop environment", error=str(e), exc_info=True)
            environment.status = EnvironmentStatus.ERROR
            environment.status_message = f"Failed to stop: {str(e)}"
            self.db.commit()
            raise

    async def restart_environment(self, environment_id: int) -> Dict[str, Any]:
        """환경 재시작"""
        log = self.log.bind(environment_id=environment_id)
        log.info("Restarting environment")
        await self.stop_environment(environment_id)
        log.info("Waiting for environment to stop before restarting")
        await asyncio.sleep(10)
        await self.start_environment(environment_id)
        log.info("Environment restarted successfully")
        return {"message": "Environment restarted successfully"}

    async def delete_environment(self, environment_id: int) -> Dict[str, Any]:
        """환경 완전 삭제"""
        log = self.log.bind(environment_id=environment_id)
        log.info("Deleting environment permanently")
        environment = self.db.query(EnvironmentInstance).filter(
            EnvironmentInstance.id == environment_id
        ).first()

        if not environment:
            log.error("Delete failed: environment not found")
            raise Exception("Environment not found")

        try:
            log.info("Deleting K8s deployment", deployment_name=environment.k8s_deployment_name)
            await self.k8s_service.delete_deployment(
                namespace=environment.k8s_namespace,
                deployment_name=environment.k8s_deployment_.name
            )

            if environment.k8s_service_name:
                log.info("Deleting K8s service", service_name=environment.k8s_service_name)
                await self.k8s_service.delete_service(
                    namespace=environment.k8s_namespace,
                    service_name=environment.k8s_service_name
                )

            log.info("Deleting environment from database")
            self.db.delete(environment)
            self.db.commit()
            log.info("Environment deleted successfully")
            return {"message": "Environment deleted successfully"}

        except Exception as e:
            log.error("Failed to delete environment", error=str(e), exc_info=True)
            raise Exception(f"Failed to delete environment: {str(e)}")