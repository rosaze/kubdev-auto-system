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
    사용자 생성 + 개발 환경 자동 생성 (실시간 로그 스트리밍) - MOCK VERSION

    실제 Kubernetes 환경을 생성하지 않고, 미리 생성된 3개의 mock 환경 중 하나를 할당합니다.
    Server-Sent Events를 사용하여 환경 생성 과정을 실시간으로 전송합니다.
    """
    async def event_generator():
        log = structlog.get_logger(__name__)

        # Mock 환경 매핑 (템플릿 ID -> 환경 ID)
        MOCK_ENV_MAP = {
            20: 22,  # Django Template -> Environment 22
            21: 23,  # React Template -> Environment 23
            22: 24,  # AI Study Template -> Environment 24
        }

        try:
            # 1. 사용자 생성 시작
            yield f"data: {json.dumps({'status': 'user_creating', 'message': '👤 사용자 계정 생성 중...'})}\n\n"
            await asyncio.sleep(0.5)  # 약간의 지연 효과

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
            await asyncio.sleep(0.8)

            # 2. 템플릿 조회 (Mock)
            yield f"data: {json.dumps({'status': 'loading_template', 'message': '📄 템플릿 정보 확인 중...'})}\n\n"
            await asyncio.sleep(0.6)

            template = db.query(ProjectTemplate).filter(ProjectTemplate.id == template_id).first()
            if not template:
                yield f"data: {json.dumps({'status': 'error', 'message': '❌ 템플릿을 찾을 수 없습니다'})}\n\n"
                return

            yield f"data: {json.dumps({'status': 'template_loaded', 'message': f'✅ 템플릿 확인 완료: {template.name}'})}\n\n"
            await asyncio.sleep(0.7)

            # 3. Mock 환경 할당
            yield f"data: {json.dumps({'status': 'allocating_env', 'message': '🔧 개발 환경 할당 중...'})}\n\n"
            await asyncio.sleep(1.0)

            # 템플릿 ID에 따라 mock 환경 선택
            mock_env_id = MOCK_ENV_MAP.get(template_id)
            if not mock_env_id:
                # 템플릿 매핑이 없으면 round-robin으로 할당
                all_users = db.query(User).filter(User.role == UserRole.USER).count()
                mock_env_id = 22 + (all_users % 3)

            mock_env = db.query(EnvironmentInstance).filter(EnvironmentInstance.id == mock_env_id).first()
            if not mock_env:
                yield f"data: {json.dumps({'status': 'error', 'message': '❌ Mock 환경을 찾을 수 없습니다'})}\n\n"
                return

            yield f"data: {json.dumps({'status': 'env_allocated', 'message': f'✅ 환경 할당 완료 (환경 ID: {mock_env_id})'})}\n\n"
            await asyncio.sleep(0.8)

            # 4. Git 저장소 클론 (Fake) - 저장소가 있을 경우에만
            if mock_env.git_repository:
                yield f"data: {json.dumps({'status': 'cloning_git', 'message': f'📦 Git 저장소 클론 중: {mock_env.git_repository}'})}\n\n"
                await asyncio.sleep(1.5)

                yield f"data: {json.dumps({'status': 'git_cloned', 'message': '✅ Git 저장소 클론 완료'})}\n\n"
                await asyncio.sleep(0.7)
            else:
                # Git 저장소가 없는 경우 (빈 workspace)
                yield f"data: {json.dumps({'status': 'setup_workspace', 'message': '📁 빈 워크스페이스 준비 중...'})}\n\n"
                await asyncio.sleep(1.0)

                yield f"data: {json.dumps({'status': 'workspace_ready', 'message': '✅ 워크스페이스 준비 완료'})}\n\n"
                await asyncio.sleep(0.5)

            # 5. 의존성 설치 (Fake)
            if mock_env.git_repository and 'django' in mock_env.git_repository.lower():
                yield f"data: {json.dumps({'status': 'installing_deps', 'message': '📦 Python 의존성 설치 중...'})}\n\n"
                await asyncio.sleep(1.2)
                yield f"data: {json.dumps({'status': 'deps_installed', 'message': '✅ pip install 완료'})}\n\n"
            elif mock_env.git_repository and 'react' in mock_env.git_repository.lower():
                yield f"data: {json.dumps({'status': 'installing_deps', 'message': '📦 npm 의존성 설치 중...'})}\n\n"
                await asyncio.sleep(1.5)
                yield f"data: {json.dumps({'status': 'deps_installed', 'message': '✅ npm install 완료'})}\n\n"
            else:
                yield f"data: {json.dumps({'status': 'preparing', 'message': '⚙️ 개발 환경 준비 중...'})}\n\n"
                await asyncio.sleep(1.0)

            await asyncio.sleep(0.5)

            # 6. VSCode 서버 시작 (Fake)
            yield f"data: {json.dumps({'status': 'starting_vscode', 'message': '🚀 VSCode 서버 시작 중...'})}\n\n"
            await asyncio.sleep(1.0)

            yield f"data: {json.dumps({'status': 'vscode_started', 'message': '✅ VSCode 서버 준비 완료'})}\n\n"
            await asyncio.sleep(0.5)

            # 7. 사용자에게 환경 연결
            # 새 환경 인스턴스 생성 (DB에만 기록, 실제 K8s는 생성 안 함)
            new_env = EnvironmentInstance(
                name=f"{user.name}'s Environment",
                template_id=template_id,
                user_id=user.id,
                k8s_namespace=mock_env.k8s_namespace,
                k8s_deployment_name=f"mock-{user.id}",
                k8s_service_name=f"svc-{user.id}",
                status=EnvironmentStatus.RUNNING,
                git_repository=mock_env.git_repository,
                git_branch=mock_env.git_branch or 'main',
                access_url=mock_env.access_url,  # Mock 환경의 URL 사용
                environment_config=template.environment_variables or {},
                port_mappings=template.exposed_ports or [],
                auto_stop_enabled=True
            )
            db.add(new_env)
            db.commit()
            db.refresh(new_env)

            log.info("Mock environment assigned",
                     user_id=user.id,
                     env_id=new_env.id,
                     mock_env_id=mock_env_id,
                     url=mock_env.access_url)

            # 8. 완료!
            completion_data = {
                'status': 'completed',
                'message': '🎉 환경 생성 완료!',
                'user_id': user.id,
                'access_code': access_code,
                'environment_id': new_env.id,
                'url': mock_env.access_url
            }
            yield f"data: {json.dumps(completion_data)}\n\n"

        except Exception as e:
            db.rollback()
            log.error("Failed to create mock environment", error=str(e), exc_info=True)
            yield f"data: {json.dumps({'status': 'error', 'message': f'❌ 생성 실패: {str(e)}'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
