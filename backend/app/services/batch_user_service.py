"""
Batch User Service
일괄 사용자 생성 및 관리 서비스 (부트캠프용)
"""

import asyncio
import secrets
import string
import time
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from app.models.user import User, UserRole
from app.models.environment import EnvironmentInstance, EnvironmentStatus
from app.models.organization import Organization
from app.models.project_template import ProjectTemplate
from app.services.kubernetes_service import KubernetesService
from app.services.environment_service import EnvironmentService
from app.core.security import get_password_hash
import logging

logger = logging.getLogger(__name__)


class BatchUserService:
    """일괄 사용자 생성 서비스"""

    def __init__(self, db: Session):
        self.db = db
        self.k8s_service = KubernetesService()

    def _generate_password(self, length: int = 12) -> str:
        """안전한 비밀번호 자동 생성"""
        characters = string.ascii_letters + string.digits + "!@#$%"
        return ''.join(secrets.choice(characters) for _ in range(length))

    def _generate_username_list(self, prefix: str, count: int) -> List[str]:
        """사용자명 목록 생성"""
        usernames = []
        for i in range(1, count + 1):
            username = f"{prefix}-{str(i).zfill(2)}"
            usernames.append(username)
        return usernames

    async def create_batch_users(
        self,
        prefix: str,
        count: int,
        template_id: int,
        organization_id: int,
        resource_quota: Dict
    ) -> Dict:
        """대량 사용자 계정 + 환경 생성"""

        start_time = time.time()
        created_users = []
        failures = []

        try:
            # 1. 사용자명 목록 생성
            usernames = self._generate_username_list(prefix, count)

            # 2. 템플릿 정보 조회
            template = self.db.query(ProjectTemplate).filter(
                ProjectTemplate.id == template_id
            ).first()

            if not template:
                raise ValueError(f"Template {template_id} not found")

            # 3. 조직 정보 확인
            organization = self.db.query(Organization).filter(
                Organization.id == organization_id
            ).first()

            if not organization:
                raise ValueError(f"Organization {organization_id} not found")

            # 4. 병렬 처리로 사용자 생성
            logger.info(f"Starting batch creation of {count} users with prefix '{prefix}'")

            # 세마포어로 동시 생성 수 제한 (최대 10개 동시)
            semaphore = asyncio.Semaphore(10)

            # 모든 사용자 생성 작업을 병렬로 실행
            tasks = []
            for username in usernames:
                task = self._create_single_user_with_semaphore(
                    semaphore=semaphore,
                    username=username,
                    template=template,
                    organization_id=organization_id,
                    resource_quota=resource_quota
                )
                tasks.append(task)

            # 모든 작업 완료 대기
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # 결과 정리
            for i, result in enumerate(results):
                username = usernames[i]

                if isinstance(result, Exception):
                    failures.append({
                        "username": username,
                        "error": str(result),
                        "timestamp": datetime.utcnow().isoformat()
                    })
                    logger.error(f"Failed to create user {username}: {str(result)}")
                else:
                    created_users.append(result)
                    logger.info(f"Successfully created user {username}")

            execution_time = time.time() - start_time

            # 결과 요약
            result_summary = {
                "created_count": len(created_users),
                "failed_count": len(failures),
                "total_requested": count,
                "users": created_users,
                "failures": failures,
                "execution_time": f"{execution_time:.2f}s",
                "average_time_per_user": f"{execution_time/count:.2f}s" if count > 0 else "0s"
            }

            logger.info(
                f"Batch creation completed: {len(created_users)}/{count} users created "
                f"in {execution_time:.2f}s"
            )

            return result_summary

        except Exception as e:
            logger.error(f"Batch user creation failed: {str(e)}")
            raise

    async def _create_single_user_with_semaphore(
        self,
        semaphore: asyncio.Semaphore,
        username: str,
        template: ProjectTemplate,
        organization_id: int,
        resource_quota: Dict
    ) -> Dict:
        """세마포어를 사용한 단일 사용자 생성"""

        async with semaphore:
            return await self._create_single_user_internal(
                username=username,
                template=template,
                organization_id=organization_id,
                resource_quota=resource_quota
            )

    async def _create_single_user_internal(
        self,
        username: str,
        template: ProjectTemplate,
        organization_id: int,
        resource_quota: Dict
    ) -> Dict:
        """내부 단일 사용자 생성 로직"""

        try:
            # 1. 사용자 계정 생성
            password = self._generate_password()
            email = f"{username}@kubdev.local"

            # 중복 확인
            existing_user = self.db.query(User).filter(User.email == email).first()
            if existing_user:
                raise ValueError(f"User {username} already exists")

            user = User(
                email=email,
                name=username,
                hashed_password=get_password_hash(password),
                role=UserRole.DEVELOPER,
                organization_id=organization_id,
                is_active=True,
                is_verified=True
            )

            self.db.add(user)
            self.db.flush()  # ID 생성을 위해 flush

            # 2. 개발 환경 인스턴스 생성
            environment_name = f"{username}-environment"
            namespace = f"kubdev-{username}"

            environment = EnvironmentInstance(
                name=environment_name,
                template_id=template.id,
                user_id=user.id,
                k8s_namespace=namespace,
                k8s_deployment_name=f"env-{username}",
                k8s_service_name=f"svc-{username}",
                k8s_ingress_name=f"ing-{username}",
                status=EnvironmentStatus.PENDING,
                environment_config=resource_quota,
                expires_at=datetime.utcnow() + timedelta(hours=8),  # 8시간 후 만료
                auto_stop_enabled=True
            )

            self.db.add(environment)
            self.db.flush()

            # 3. K8s 리소스 생성
            try:
                await self._create_kubernetes_resources(
                    environment=environment,
                    template=template,
                    resource_quota=resource_quota
                )

                # 환경 상태 업데이트
                environment.status = EnvironmentStatus.CREATING
                environment.access_url = f"https://{username}.ide.kubdev.io"

            except Exception as k8s_error:
                environment.status = EnvironmentStatus.ERROR
                environment.status_message = f"K8s creation failed: {str(k8s_error)}"
                logger.error(f"K8s resource creation failed for {username}: {str(k8s_error)}")

            # 4. 데이터베이스 커밋
            self.db.commit()

            # 5. 결과 반환
            return {
                "username": username,
                "email": email,
                "password": password,
                "user_id": user.id,
                "environment_id": environment.id,
                "namespace": namespace,
                "access_url": environment.access_url,
                "status": environment.status.value,
                "expires_at": environment.expires_at.isoformat(),
                "created_at": datetime.utcnow().isoformat()
            }

        except Exception as e:
            self.db.rollback()
            raise Exception(f"Failed to create user {username}: {str(e)}")

    async def _create_kubernetes_resources(
        self,
        environment: EnvironmentInstance,
        template: ProjectTemplate,
        resource_quota: Dict
    ):
        """Kubernetes 리소스 생성"""

        try:
            namespace = environment.k8s_namespace
            deployment_name = environment.k8s_deployment_name

            # 1. 네임스페이스 생성
            await self.k8s_service.create_namespace(namespace)

            # 2. ResourceQuota 생성
            await self.k8s_service.create_resource_quota(
                namespace=namespace,
                quota_name=f"quota-{deployment_name}",
                cpu_limit=resource_quota.get("cpu", "1"),
                memory_limit=resource_quota.get("memory", "2Gi"),
                storage_limit=resource_quota.get("storage", "10Gi"),
                pod_limit=5
            )

            # 3. Deployment 생성
            await self.k8s_service.create_deployment(
                namespace=namespace,
                deployment_name=deployment_name,
                image=template.base_image,
                environment_vars=template.environment_variables or {},
                resource_limits=template.resource_limits or resource_quota,
                git_repo=template.default_git_repo,
                git_branch=template.git_branch or "main"
            )

            # 4. Service 생성
            await self.k8s_service.create_service(
                namespace=namespace,
                service_name=environment.k8s_service_name,
                deployment_name=deployment_name,
                port=8080  # VS Code Server 포트
            )

            # 5. Ingress 생성
            await self.k8s_service.create_ingress(
                namespace=namespace,
                ingress_name=environment.k8s_ingress_name,
                service_name=environment.k8s_service_name,
                host=f"{environment.name.replace('_', '-').lower()}.ide.kubdev.io",
                service_port=8080
            )

            logger.info(f"K8s resources created successfully for {namespace}")

        except Exception as e:
            logger.error(f"K8s resource creation failed for {namespace}: {str(e)}")
            raise

    async def create_single_user_with_environment(
        self,
        username: str,
        template_id: int,
        organization_id: int,
        resource_quota: Dict,
        custom_password: Optional[str] = None
    ) -> Dict:
        """단일 사용자 + 환경 생성 (API 엔드포인트용)"""

        try:
            template = self.db.query(ProjectTemplate).filter(
                ProjectTemplate.id == template_id
            ).first()

            if not template:
                return {"success": False, "error": "Template not found"}

            # 비밀번호 설정
            password = custom_password or self._generate_password()

            # 사용자 생성
            result = await self._create_single_user_internal(
                username=username,
                template=template,
                organization_id=organization_id,
                resource_quota=resource_quota
            )

            # 비밀번호 오버라이드 (커스텀 비밀번호인 경우)
            if custom_password:
                result["password"] = custom_password

            return {
                "success": True,
                "user": {
                    "username": result["username"],
                    "email": result["email"],
                    "password": result["password"],
                    "user_id": result["user_id"]
                },
                "environment": {
                    "environment_id": result["environment_id"],
                    "namespace": result["namespace"],
                    "status": result["status"],
                    "expires_at": result["expires_at"]
                },
                "access_info": {
                    "access_url": result["access_url"],
                    "username": result["username"],
                    "password": result["password"]
                }
            }

        except Exception as e:
            logger.error(f"Single user creation failed: {str(e)}")
            return {"success": False, "error": str(e)}

    async def delete_batch_users(
        self,
        user_ids: List[int],
        dry_run: bool = True
    ) -> Dict:
        """일괄 사용자 삭제"""

        deleted_count = 0
        failed_count = 0
        details = []

        try:
            for user_id in user_ids:
                user = self.db.query(User).filter(User.id == user_id).first()

                if not user:
                    failed_count += 1
                    details.append({
                        "user_id": user_id,
                        "status": "failed",
                        "reason": "User not found"
                    })
                    continue

                detail = {
                    "user_id": user_id,
                    "username": user.email.split("@")[0],
                    "email": user.email
                }

                if dry_run:
                    detail["status"] = "would_delete"
                    detail["environments"] = len(user.environments)
                else:
                    try:
                        # 사용자의 모든 환경 삭제
                        env_service = EnvironmentService(self.db)
                        for env in user.environments:
                            await env_service.delete_environment(env.id)

                        # 사용자 삭제
                        self.db.delete(user)
                        self.db.commit()

                        detail["status"] = "deleted"
                        deleted_count += 1

                    except Exception as delete_error:
                        self.db.rollback()
                        detail["status"] = "failed"
                        detail["reason"] = str(delete_error)
                        failed_count += 1

                details.append(detail)

            return {
                "deleted_count": deleted_count,
                "failed_count": failed_count,
                "details": details
            }

        except Exception as e:
            logger.error(f"Batch deletion failed: {str(e)}")
            raise

    def get_batch_creation_statistics(self) -> Dict:
        """일괄 생성 통계"""

        try:
            # 최근 24시간 생성된 사용자
            recent_users = self.db.query(User).filter(
                User.created_at >= datetime.utcnow() - timedelta(hours=24)
            ).all()

            # prefix별 통계
            prefix_stats = {}
            for user in recent_users:
                username = user.email.split("@")[0]
                if "-" in username:
                    prefix = username.split("-")[0]
                    if prefix not in prefix_stats:
                        prefix_stats[prefix] = 0
                    prefix_stats[prefix] += 1

            return {
                "recent_24h_users": len(recent_users),
                "prefix_statistics": prefix_stats,
                "total_users": self.db.query(User).count(),
                "timestamp": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Failed to get batch statistics: {str(e)}")
            return {"error": str(e)}