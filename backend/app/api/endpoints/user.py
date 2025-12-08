"""
User API Endpoints
사용자 관련 API 엔드포인트
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List
import logging
import os
import structlog
import re
import unicodedata
import json
import asyncio

from app.core.database import get_db
from app.core.dependencies import get_current_active_user
from app.core.security import generate_access_code
from app.models.user import User, UserRole
from app.models.project_template import ProjectTemplate, TemplateStatus
from app.models.environment import EnvironmentInstance, EnvironmentStatus
from app.schemas.user import (
    UserCreateAdmin,
    UserCreateAdminResponse,
    UserCreateUser,
    UserCreateUserResponse,
    UserCreateWithEnvironment,
    UserCreateWithEnvironmentResponse,
)
from app.services.kubernetes_service import KubernetesService
from app.services.environment_service import EnvironmentService

logger = logging.getLogger(__name__)

router = APIRouter()


def sanitize_name_for_k8s(name: str) -> str:
    """
    사용자 이름을 Kubernetes RFC 1123 호환 형식으로 변환
    - 소문자 영문자, 숫자, 하이픈만 허용
    - 영문자 또는 숫자로 시작하고 끝나야 함
    """
    # Unicode 정규화 (한글 등 → 로마자 변환 시도)
    normalized = unicodedata.normalize('NFKD', name)
    # ASCII로 변환 가능한 문자만 추출
    ascii_str = normalized.encode('ASCII', 'ignore').decode('ASCII')

    # 공백을 하이픈으로 변환
    sanitized = ascii_str.replace(' ', '-')
    # 소문자로 변환
    sanitized = sanitized.lower()
    # 영문자, 숫자, 하이픈만 남기기
    sanitized = re.sub(r'[^a-z0-9-]', '', sanitized)
    # 연속된 하이픈 제거
    sanitized = re.sub(r'-+', '-', sanitized)
    # 앞뒤 하이픈 제거
    sanitized = sanitized.strip('-')

    # 비어있으면 기본값 사용
    if not sanitized:
        sanitized = "user"

    # 영문자 또는 숫자로 시작하도록 보장
    if sanitized and not sanitized[0].isalnum():
        sanitized = 'u' + sanitized

    # 최대 63자로 제한 (Kubernetes label 규칙)
    sanitized = sanitized[:63]

    return sanitized


@router.post("/admin", response_model=UserCreateAdminResponse, status_code=status.HTTP_201_CREATED)
async def create_admin_user(
    user_data: UserCreateAdmin,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
) -> UserCreateAdminResponse:
    """
    사용자 생성 - 관계자
    """
    logger.info(f"Creating admin user: {user_data.name} by user {user_data.current_user_id}")
    
    # 현재 사용자가 관리자인지 확인
    if current_user.role != UserRole.ADMIN:
        logger.warning(f"Non-admin user {current_user.id} attempted to create admin user")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can create admin users"
        )
    
    # 5자리 접속 코드 생성 (중복 방지)
    max_attempts = 10
    access_code = None
    
    for _ in range(max_attempts):
        code = generate_access_code(length=5)
        # 중복 확인
        existing_user = db.query(User).filter(User.hashed_password == code).first()
        if not existing_user:
            access_code = code
            break
    
    if not access_code:
        logger.error("Failed to generate unique access code after multiple attempts")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate unique access code"
        )
    
    # 새 관리자 사용자 생성
    new_user = User(
        name=user_data.name,
        hashed_password=access_code,  # 개발 중이므로 접속 코드를 그대로 저장
        role=UserRole.ADMIN,
        is_active=True,
        created_by=user_data.current_user_id
    )
    
    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        logger.info(f"Admin user created successfully: ID={new_user.id}, access_code={access_code}")
        
        return UserCreateAdminResponse(
            id=new_user.id,
            name=new_user.name,
            role=new_user.role,
            access_code=access_code,
            is_active=new_user.is_active,
            created_at=new_user.created_at
        )
    
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create admin user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create admin user: {str(e)}"
        )


@router.post("/user", response_model=UserCreateUserResponse, status_code=status.HTTP_201_CREATED)
async def create_regular_user(
    user_data: UserCreateUser,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
) -> UserCreateUserResponse:
    """
    사용자 생성 - 일반 사용자 (환경 자동 생성 포함)
    """
    logger.info(f"Creating regular user: {user_data.name} by user {user_data.current_user_id}")
    
    # 현재 사용자가 관리자인지 확인
    if current_user.role != UserRole.ADMIN:
        logger.warning(f"Non-admin user {current_user.id} attempted to create regular user")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can create users"
        )
    
    # 5자리 접속 코드 생성 (중복 방지)
    max_attempts = 10
    access_code = None
    
    for _ in range(max_attempts):
        code = generate_access_code(length=5)
        # 중복 확인
        existing_user = db.query(User).filter(User.hashed_password == code).first()
        if not existing_user:
            access_code = code
            break
    
    if not access_code:
        logger.error("Failed to generate unique access code after multiple attempts")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate unique access code"
        )
    
    # 새 일반 사용자 생성
    new_user = User(
        name=user_data.name,
        hashed_password=access_code,
        role=UserRole.USER,
        is_active=True,
        created_by=user_data.current_user_id
    )
    
    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        logger.info(f"User created successfully: ID={new_user.id}, access_code={access_code}")
        
        # 아무 ACTIVE 템플릿 조회 (관리자는 모든 템플릿 사용 가능)
        template = db.query(ProjectTemplate).filter(
            ProjectTemplate.status == TemplateStatus.ACTIVE
        ).first()

        if not template:
            logger.error(f"No active template found in the system")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No active template found. Please create a template first."
            )
        
        logger.info(f"Using template: ID={template.id}, name={template.name}")
        
        # Environment 생성
        k8s_namespace = f"user-{new_user.id}"
        k8s_deployment_name = f"env-{new_user.id}-{template.id}"
        
        new_environment = EnvironmentInstance(
            name=f"{new_user.name}'s Environment",
            template_id=template.id,
            user_id=new_user.id,
            k8s_namespace=k8s_namespace,
            k8s_deployment_name=k8s_deployment_name,
            k8s_service_name=f"svc-{new_user.id}",
            status=EnvironmentStatus.PENDING,
            environment_config=template.environment_variables or {},
            port_mappings=template.exposed_ports or [],
            auto_stop_enabled=True
        )
        
        db.add(new_environment)
        db.commit()
        db.refresh(new_environment)
        
        logger.info(f"Environment created successfully: ID={new_environment.id}, namespace={k8s_namespace}")

        # KubeDevEnvironment CRD 생성 (컨트롤러가 자동으로 환경 프로비저닝)
        k8s_service = KubernetesService()
        try:
            # CRD 이름은 고유해야 함
            crd_name = f"env-user-{new_user.id}"
            crd_namespace = "kubdev-users"  # 모든 CRD는 kubdev-users 네임스페이스에 생성

            # 템플릿에서 리소스 제한 추출
            cpu_limit = template.resource_limits.get("cpu", "1000m") if template.resource_limits else "1000m"
            memory_limit = template.resource_limits.get("memory", "2Gi") if template.resource_limits else "2Gi"
            service_port = template.exposed_ports[0] if template.exposed_ports else 8080

            # KubeDevEnvironment CRD 객체 생성
            crd_object = {
                "apiVersion": "kubedev.my-project.com/v1alpha1",
                "kind": "KubeDevEnvironment",
                "metadata": {
                    "name": crd_name,
                    "namespace": crd_namespace
                },
                "spec": {
                    "userName": new_user.name,
                    "gitRepository": template.default_git_repo or "",
                    "image": template.base_image,
                    "commands": {
                        "init": "\n".join(template.init_scripts) if template.init_scripts else "",
                        "start": "\n".join(template.post_start_commands) if template.post_start_commands else ""
                    },
                    "ports": template.exposed_ports or [8080],
                    "storage": {
                        "size": template.resource_limits.get("storage", "10Gi") if template.resource_limits else "10Gi"
                    }
                }
            }

            # CRD 생성
            logger.info(f"Creating KubeDevEnvironment CRD: {crd_name}")
            await k8s_service.create_custom_object(crd_object)

            # Environment DB 업데이트 (CRD가 생성되면 컨트롤러가 처리)
            new_environment.k8s_namespace = crd_namespace
            new_environment.k8s_deployment_name = crd_name
            new_environment.status = EnvironmentStatus.CREATING
            new_environment.external_port = service_port
            db.commit()
            db.refresh(new_environment)

            logger.info(f"KubeDevEnvironment CRD created for environment {new_environment.id}")

        except Exception as k8s_error:
            logger.error(f"Failed to create KubeDevEnvironment CRD: {str(k8s_error)}")
            # CRD 생성 실패 시 환경 상태를 ERROR로 업데이트
            new_environment.status = EnvironmentStatus.ERROR
            new_environment.status_message = f"CRD creation failed: {str(k8s_error)}"
            db.commit()
            db.refresh(new_environment)
        
        # 응답 데이터 구성
        environment_data = UserCreateUserResponse.EnvironmentData(
            id=new_environment.id,
            template_id=template.id,
            user_id=new_user.id,
            status=new_environment.status.value,
            port=new_environment.external_port or 0,
            cpu=int(template.resource_limits.get("cpu", "1000m").replace("m", "")) if template.resource_limits else 1000,
            memory=int(template.resource_limits.get("memory", "2Gi").replace("Gi", "")) * 1024 if template.resource_limits else 2048
        )
        
        user_info = UserCreateUserResponse.UserData(
            id=new_user.id,
            name=new_user.name,
            role=new_user.role,
            access_code=access_code,
            is_active=new_user.is_active,
            created_at=new_user.created_at
        )
        
        return UserCreateUserResponse(
            user=user_info,
            environment=environment_data
        )
    
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create regular user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create regular user: {str(e)}"
        )


# 템플릿 ID와 YAML 파일 매핑
# TODO: 나중에 DB에 저장하거나 설정 파일로 관리
TEMPLATE_YAML_MAP = {
    1: "demo_nodejs_working.yaml",
    2: "demo_python_ml.yaml",
    3: "demo_bash_simple.yaml",
}


@router.post("/user-with-environment", response_model=UserCreateWithEnvironmentResponse, status_code=status.HTTP_201_CREATED)
async def create_user_with_environment(
    user_data: UserCreateWithEnvironment,
    db: Session = Depends(get_db)
) -> UserCreateWithEnvironmentResponse:
    """
    사용자 생성 + 개발 환경 자동 생성 (Admin용)

    템플릿을 선택하면 해당 템플릿의 YAML 파일로 환경을 자동 생성합니다.
    Template : User = 1:1 관계
    """
    log = structlog.get_logger(__name__)
    log.info("Creating user with environment", name=user_data.name, template_id=user_data.template_id)

    try:
        # 1. 사용자 계정 생성
        access_code = generate_access_code()

        # 중복 코드 확인
        max_attempts = 10
        for _ in range(max_attempts):
            existing = db.query(User).filter(User.hashed_password == access_code).first()
            if not existing:
                break
            access_code = generate_access_code()
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate unique access code"
            )

        user = User(
            name=user_data.name,
            role=UserRole.USER,
            hashed_password=access_code,
            is_active=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        log.info("User created successfully", user_id=user.id, access_code=access_code)

        # 2. 템플릿에 해당하는 YAML 파일 찾기
        yaml_filename = TEMPLATE_YAML_MAP.get(user_data.template_id)
        if not yaml_filename:
            db.rollback()
            log.error("Template YAML mapping not found", template_id=user_data.template_id)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Template ID {user_data.template_id}에 해당하는 YAML 파일이 없습니다."
            )

        # 3. YAML 파일 읽기
        yaml_file_path = os.path.join(os.getcwd(), yaml_filename)
        if not os.path.exists(yaml_file_path):
            db.rollback()
            log.error("YAML file not found", path=yaml_file_path)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"YAML 파일을 찾을 수 없습니다: {yaml_filename}"
            )

        with open(yaml_file_path, 'rb') as f:
            yaml_content = f.read()

        log.info("YAML file loaded", filename=yaml_filename)

        # 4. 환경 생성 (공통 함수 재활용)
        env_service = EnvironmentService(db, log)
        result = await env_service.create_environment_from_yaml(
            template_id=user_data.template_id,
            user=user,
            yaml_content=yaml_content
        )

        log.info("Environment created successfully",
                user_id=user.id,
                environment_id=result["environment_id"])

        return UserCreateWithEnvironmentResponse(
            user_id=user.id,
            access_code=access_code,
            environment_id=result["environment_id"],
            environment_status=result["environment_status"]
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        log.error("Failed to create user with environment", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"사용자 및 환경 생성 실패: {str(e)}"
        )

@router.get("/user-with-environment/stream")
async def create_user_with_environment_stream(
    name: str = Query(..., description="사용자 이름"),
    template_id: int = Query(..., description="템플릿 ID"),
    db: Session = Depends(get_db)
):
    """
    사용자 생성 + 개발 환경 자동 생성 (실시간 로그 스트리밍)

    Server-Sent Events를 사용하여 환경 생성 과정을 실시간으로 전송합니다.
    """
    async def event_generator():
        log = structlog.get_logger(__name__)

        try:
            # 1. 사용자 생성 시작
            yield f"data: {json.dumps({'status': 'user_creating', 'message': '👤 사용자 계정 생성 중...'})}\n\n"

            access_code = generate_access_code()
            max_attempts = 10
            for _ in range(max_attempts):
                existing = db.query(User).filter(User.hashed_password == access_code).first()
                if not existing:
                    break
                access_code = generate_access_code()
            else:
                yield f"data: {json.dumps({'status': 'error', 'message': '❌ 접속 코드 생성 실패'})}\n\n"
                return

            user = User(
                name=name,
                role=UserRole.USER,
                hashed_password=access_code,
                is_active=True
            )
            db.add(user)
            db.commit()
            db.refresh(user)

            yield f"data: {json.dumps({'status': 'user_created', 'message': f'✅ 사용자 생성 완료 (ID: {user.id}, 접속코드: {access_code})'})}\n\n"
            log.info("User created successfully", user_id=user.id, access_code=access_code)

            # 2. YAML 파일 로드
            yield f"data: {json.dumps({'status': 'loading_template', 'message': '📄 템플릿 파일 로드 중...'})}\n\n"

            yaml_filename = TEMPLATE_YAML_MAP.get(template_id)
            if not yaml_filename:
                db.rollback()
                yield f"data: {json.dumps({'status': 'error', 'message': '❌ 템플릿 파일을 찾을 수 없습니다'})}\n\n"
                return

            yaml_file_path = os.path.join(os.getcwd(), yaml_filename)
            if not os.path.exists(yaml_file_path):
                db.rollback()
                yield f"data: {json.dumps({'status': 'error', 'message': f'❌ YAML 파일 없음: {yaml_filename}'})}\n\n"
                return

            with open(yaml_file_path, 'rb') as f:
                yaml_content = f.read()

            yield f"data: {json.dumps({'status': 'template_loaded', 'message': f'✅ 템플릿 로드 완료: {yaml_filename}'})}\n\n"

            # 3. Kubernetes CRD 생성
            yield f"data: {json.dumps({'status': 'creating_crd', 'message': '☸️  Kubernetes CRD 생성 중...'})}\n\n"

            env_service = EnvironmentService(db, log)
            result = await env_service.create_environment_from_yaml(
                template_id=template_id,
                user=user,
                yaml_content=yaml_content
            )

            env_id = result["environment_id"]
            yield f"data: {json.dumps({'status': 'crd_created', 'message': f'✅ CRD 생성 완료 (환경 ID: {env_id})'})}\n\n"

            # 4. Pod 상태 확인 (최대 90초 대기, 2초 간격)
            yield f"data: {json.dumps({'status': 'waiting_pod', 'message': '⏳ Pod 생성 대기 중...'})}\n\n"

            k8s_service = KubernetesService()
            namespace = f"kubedev-{user.name.lower()}-env-user-{user.id}"

            # Notification service import
            from app.services.notification_service import notification_service

            for i in range(45):  # 90초 / 2초 = 45번 체크
                await asyncio.sleep(2)  # 2초마다 체크 (부하 감소)
                try:
                    # Pod 상태 확인
                    pods = k8s_service.v1.list_namespaced_pod(namespace=namespace)
                    if pods.items:
                        pod = pods.items[0]
                        phase = pod.status.phase

                        if phase == "Pending":
                            if i % 5 == 0:  # 10초마다만 로그 출력
                                yield f"data: {json.dumps({'status': 'pod_pending', 'message': f'⏳ Pod 시작 중... ({(i+1)*2}초)'})}\n\n"
                        elif phase == "Running":
                            yield f"data: {json.dumps({'status': 'pod_running', 'message': '🚀 Pod 실행 중!'})}\n\n"

                            # Service URL 확인
                            services = k8s_service.v1.list_namespaced_service(namespace=namespace)
                            if services.items:
                                svc = services.items[0]
                                # NodePort 또는 ClusterIP 정보 추출
                                port = svc.spec.ports[0].node_port if svc.spec.type == "NodePort" else svc.spec.ports[0].port
                                url = f"http://localhost:{port}"

                                # 웹훅 알림 전송
                                await notification_service.send_slack_notification(
                                    f"🎉 개발 환경 생성 완료!\n"
                                    f"• 사용자: {user.name}\n"
                                    f"• 접속 코드: {access_code}\n"
                                    f"• 환경 ID: {env_id}\n"
                                    f"• URL: {url}"
                                )

                                yield f"data: {json.dumps({'status': 'completed', 'message': '🎉 환경 생성 완료!', 'user_id': user.id, 'access_code': access_code, 'environment_id': env_id, 'url': url})}\n\n"
                                return
                            else:
                                # Service가 없어도 완료 처리
                                await notification_service.send_slack_notification(
                                    f"🎉 개발 환경 생성 완료!\n"
                                    f"• 사용자: {user.name}\n"
                                    f"• 접속 코드: {access_code}\n"
                                    f"• 환경 ID: {env_id}"
                                )

                                yield f"data: {json.dumps({'status': 'completed', 'message': '🎉 환경 생성 완료!', 'user_id': user.id, 'access_code': access_code, 'environment_id': env_id})}\n\n"
                                return
                        elif phase == "Failed":
                            yield f"data: {json.dumps({'status': 'error', 'message': '❌ Pod 시작 실패'})}\n\n"
                            return
                except Exception as e:
                    # Namespace가 아직 없을 수 있음
                    if i < 5:  # 처음 10초만 대기 메시지
                        yield f"data: {json.dumps({'status': 'waiting_namespace', 'message': f'⏳ Namespace 생성 대기 중... ({(i+1)*2}초)'})}\n\n"
                    elif i % 10 == 0:  # 20초마다 상태 체크 로그
                        yield f"data: {json.dumps({'status': 'checking', 'message': f'⏳ 환경 확인 중... ({(i+1)*2}초)'})}\n\n"

            # 타임아웃 - 하지만 환경은 생성된 상태
            yield f"data: {json.dumps({'status': 'timeout', 'message': '⏱️ Pod 시작 대기 시간 초과 (환경은 백그라운드에서 계속 생성 중)', 'user_id': user.id, 'access_code': access_code, 'environment_id': env_id})}\n\n"

        except Exception as e:
            db.rollback()
            log.error("Failed to create user with environment", error=str(e), exc_info=True)
            yield f"data: {json.dumps({'status': 'error', 'message': f'❌ 생성 실패: {str(e)}'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
