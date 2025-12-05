"""
Environment Service
개발 환경 생명주기 관리 서비스
"""

import asyncio
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import structlog
import yaml

from app.models.environment import EnvironmentInstance, EnvironmentStatus
from app.models.project_template import ProjectTemplate
from app.models.user import User
from app.services.kubernetes_service import KubernetesService
from app.services.notification_service import notification_service
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

            # Git 리포지토리 자동 클론 설정
            if environment.git_repository:
                git_branch = environment.git_branch or "main"

                # Git 관련 환경변수 추가
                env_vars.update({
                    "GIT_REPO": environment.git_repository,
                    "GIT_BRANCH": git_branch,
                    "WORKSPACE": "/workspace",
                    "AUTO_CLONE_GIT": "true"
                })

                # Git 클론 스크립트를 환경변수로 전달 (컨테이너 시작시 실행됨)
                git_clone_script = f"""#!/bin/bash
echo "🚀 KubeDev Auto System - Git 리포지토리 자동 설정 시작"

# 작업 디렉토리 생성
mkdir -p /workspace
cd /workspace

# 기존 리포지토리가 있는지 확인
if [ -d "/workspace/.git" ]; then
    echo "📁 기존 Git 리포지토리 발견 - 업데이트 중..."
    git fetch origin
    git checkout {git_branch}
    git pull origin {git_branch}
else
    echo "📥 Git 리포지토리 클론 중: {environment.git_repository}"
    git clone -b {git_branch} {environment.git_repository} .
    echo "✅ Git 리포지토리 클론 완료"
fi

# Git 사용자 설정 (VS Code에서 사용)
git config --global user.name "KubeDev User"
git config --global user.email "user@kubdev.local"
git config --global init.defaultBranch main

# 권한 설정
chmod -R 755 /workspace
chown -R 1000:1000 /workspace

echo "🎉 Git 리포지토리 설정 완료!"
echo "📂 리포지토리: {environment.git_repository}"
echo "🌿 브랜치: {git_branch}"
echo "📁 작업 경로: /workspace"
"""

                env_vars["GIT_CLONE_SCRIPT"] = git_clone_script
                log.info("Git auto-clone configured", repo=environment.git_repository, branch=git_branch)

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
        """환경 중지 - Deployment를 0으로 스케일 다운"""
        log = self.log.bind(environment_id=environment_id)
        log.info("Stopping environment by scaling down to 0")
        environment = self.db.query(EnvironmentInstance).filter(
            EnvironmentInstance.id == environment_id
        ).first()

        if not environment:
            log.error("Stop failed: environment not found")
            raise Exception("Environment not found")

        try:
            log.info("Scaling deployment to 0 to stop environment", deployment_name=environment.k8s_deployment_name)
            await self.k8s_service.scale_deployment(
                namespace=environment.k8s_namespace,
                deployment_name=environment.k8s_deployment_name,
                replicas=0
            )

            environment.status = EnvironmentStatus.STOPPED
            environment.stopped_at = datetime.utcnow()
            environment.status_message = "Environment stopped - scaled down to 0"
            self.db.commit()
            log.info("Environment stopped successfully")
            
            # 슬랙 알림 전송
            try:
                message = f"✅ 환경 중지: '{environment.name}' (ID: {environment.id}, 사용자: {environment.user.name})이(가) 중지되었습니다."
                await notification_service.send_slack_notification(message)
            except Exception as notify_error:
                log.error("Failed to send Slack notification for stop event", error=str(notify_error))

            return {"message": "Environment stopped successfully - scaled down to 0"}

        except Exception as e:
            log.error("Failed to stop environment", error=str(e), exc_info=True)
            environment.status = EnvironmentStatus.ERROR
            environment.status_message = f"Failed to stop: {str(e)}"
            self.db.commit()
            raise

    async def restart_environment(self, environment_id: int) -> Dict[str, Any]:
        """환경 재시작 - Deployment 스케일 다운 후 스케일 업으로 Pod 재생성"""
        log = self.log.bind(environment_id=environment_id)
        log.info("Restarting environment")
        environment = self.db.query(EnvironmentInstance).filter(
            EnvironmentInstance.id == environment_id
        ).first()

        if not environment:
            log.error("Restart failed: environment not found")
            raise Exception("Environment not found")

        try:
            # 1단계: 0으로 스케일 다운
            log.info("Scaling deployment to 0 for restart", deployment_name=environment.k8s_deployment_name)
            await self.k8s_service.scale_deployment(
                namespace=environment.k8s_namespace,
                deployment_name=environment.k8s_deployment_name,
                replicas=0
            )

            # 짧은 대기 (Pod 종료 시간)
            await asyncio.sleep(5)

            # 2단계: 1로 스케일 업 (Pod 재생성 및 PVC 재마운트)
            log.info("Scaling deployment to 1 for restart", deployment_name=environment.k8s_deployment_name)
            await self.k8s_service.scale_deployment(
                namespace=environment.k8s_namespace,
                deployment_name=environment.k8s_deployment_name,
                replicas=1
            )

            environment.status = EnvironmentStatus.RUNNING
            environment.status_message = "Environment restarted successfully"
            self.db.commit()
            log.info("Environment restarted successfully")
            return {"message": "Environment restarted successfully - Pod recreated with PVC remount"}

        except Exception as e:
            log.error("Failed to restart environment", error=str(e), exc_info=True)
            environment.status = EnvironmentStatus.ERROR
            environment.status_message = f"Failed to restart: {str(e)}"
            self.db.commit()
            raise

    async def delete_environment(self, environment_id: int) -> Dict[str, Any]:
        """환경 완전 삭제 - Namespace 전체 삭제로 모든 리소스 회수"""
        log = self.log.bind(environment_id=environment_id)
        log.info("Deleting environment permanently - deleting entire namespace")
        environment = self.db.query(EnvironmentInstance).filter(
            EnvironmentInstance.id == environment_id
        ).first()

        if not environment:
            log.error("Delete failed: environment not found")
            raise Exception("Environment not found")

        try:
            # 네임스페이스 전체 삭제 (모든 리소스 자동 정리)
            log.info("Deleting entire namespace to clean up all resources", namespace=environment.k8s_namespace)
            await self.k8s_service.delete_namespace(environment.k8s_namespace)

            # 슬랙 알림 전송 (DB에서 삭제되기 전에 정보 사용)
            try:
                message = f"🗑️ 환경 삭제: '{environment.name}' (ID: {environment.id}, 사용자: {environment.user.name})이(가) 영구적으로 삭제되었습니다."
                await notification_service.send_slack_notification(message)
            except Exception as notify_error:
                log.error("Failed to send Slack notification for delete event", error=str(notify_error))

            # 데이터베이스에서 환경 기록 삭제
            log.info("Deleting environment from database")
            self.db.delete(environment)
            self.db.commit()
            log.info("Environment deleted successfully")
            return {"message": "Environment deleted successfully - namespace and all resources removed"}

        except Exception as e:
            log.error("Failed to delete environment", error=str(e), exc_info=True)
            raise Exception(f"Failed to delete environment: {str(e)}")

    async def create_environment_from_yaml(
        self,
        template_id: int,
        user: User,
        yaml_content: bytes
    ) -> Dict[str, Any]:
        """
        YAML 파일로 환경 생성 (재사용 가능한 공통 함수)

        Args:
            template_id: 템플릿 ID
            user: 사용자 객체
            yaml_content: YAML 파일 바이트 내용

        Returns:
            환경 생성 결과 (environment_id, status 등)
        """
        log = self.log.bind(user_id=user.id, template_id=template_id)
        log.info("Creating environment from YAML")

        # 1. 템플릿 존재 확인
        template = self.db.query(ProjectTemplate).filter(
            ProjectTemplate.id == template_id
        ).first()

        if not template:
            log.warning("Template not found", template_id=template_id)
            raise Exception(f"ProjectTemplate with id {template_id} not found.")

        # 2. YAML 파일 디코딩
        try:
            yaml_string = yaml_content.decode("utf-8")
        except UnicodeDecodeError:
            try:
                yaml_string = yaml_content.decode("cp949")
                log.info("Decoded YAML file using cp949 encoding as a fallback.")
            except UnicodeDecodeError:
                log.error("Failed to decode YAML file with both utf-8 and cp949.", exc_info=True)
                raise Exception("Could not decode file. Please ensure it is saved with UTF-8 or CP949 encoding.")

        # 3. YAML 파싱 및 검증
        try:
            custom_object = yaml.safe_load(yaml_string)
            if not isinstance(custom_object, dict):
                raise Exception("Invalid YAML format: not a dictionary.")

            api_version = custom_object.get("apiVersion")
            kind = custom_object.get("kind")
            if api_version != "kubedev.my-project.com/v1alpha1" or kind != "KubeDevEnvironment":
                raise Exception("Invalid YAML: apiVersion or kind does not match KubeDevEnvironment CRD.")

            # userName 주입/덮어쓰기 (보안을 위해)
            # Kubernetes 호환성을 위해 sanitize
            import re
            import unicodedata

            def sanitize_for_k8s(name: str) -> str:
                """Kubernetes RFC 1123 호환 이름으로 변환"""
                normalized = unicodedata.normalize('NFKD', name)
                ascii_str = normalized.encode('ASCII', 'ignore').decode('ASCII')
                sanitized = ascii_str.replace(' ', '-').lower()
                sanitized = re.sub(r'[^a-z0-9-]', '', sanitized)
                sanitized = re.sub(r'-+', '-', sanitized).strip('-')
                if not sanitized or not sanitized[0].isalnum():
                    sanitized = f"user-{user.id}"
                return sanitized[:63]

            if "spec" not in custom_object:
                custom_object["spec"] = {}

            # 원래 이름과 sanitize된 이름 모두 저장
            sanitized_name = sanitize_for_k8s(user.name)
            custom_object["spec"]["userName"] = sanitized_name
            log.info(f"Injected/overwrote userName '{user.name}' -> '{sanitized_name}' into CRD spec.")

            # metadata.name을 고유하게 변경 (user_id 기반)
            if "metadata" not in custom_object:
                custom_object["metadata"] = {}
            unique_crd_name = f"env-user-{user.id}"
            custom_object["metadata"]["name"] = unique_crd_name
            log.info(f"Generated unique CRD name: {unique_crd_name}")

        except yaml.YAMLError as e:
            raise Exception(f"YAML parsing error: {str(e)}")

        # 4. Kubernetes에 CRD 적용
        try:
            api_response = await self.k8s_service.create_custom_object(custom_object)
            log.info("Successfully applied KubeDevEnvironment CRD to Kubernetes.",
                    crd_name=custom_object.get("metadata", {}).get("name"))

            # 5. DB에 환경 레코드 생성
            env_name = custom_object.get("metadata", {}).get("name")
            environment = EnvironmentInstance(
                name=env_name,
                template_id=template_id,
                user_id=user.id,
                k8s_namespace=custom_object.get("metadata", {}).get("namespace", "default"),
                k8s_deployment_name=env_name,
                status=EnvironmentStatus.CREATING,
                git_repository=custom_object.get("spec", {}).get("gitRepository")
            )
            self.db.add(environment)
            self.db.commit()
            self.db.refresh(environment)
            log.info("Environment DB instance created for tracking.", environment_id=environment.id)

            return {
                "status": "success",
                "message": "KubeDevEnvironment custom resource created successfully.",
                "environment_id": environment.id,
                "crd_name": custom_object.get("metadata", {}).get("name"),
                "namespace": custom_object.get("metadata", {}).get("namespace", "default"),
                "environment_status": environment.status.value
            }

        except Exception as e:
            log.error("Failed to apply CRD to Kubernetes or create DB record", error=str(e), exc_info=True)
            self.db.rollback()
            raise Exception(f"Failed to create environment: {str(e)}")