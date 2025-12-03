"""
User API Endpoints
사용자 관련 API 엔드포인트
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import logging

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
)
from app.services.kubernetes_service import KubernetesService

logger = logging.getLogger(__name__)

router = APIRouter()


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
        
        # 현재 로그인한 사용자가 생성한 템플릿 조회
        template = db.query(ProjectTemplate).filter(
            ProjectTemplate.created_by == user_data.current_user_id,
            ProjectTemplate.status == TemplateStatus.ACTIVE
        ).first()
        
        if not template:
            logger.error(f"No active template found for user {user_data.current_user_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No active template found for current user"
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
        
        # 실제 Kubernetes 리소스 생성
        k8s_service = KubernetesService()
        try:
            # 1. Namespace 생성
            await k8s_service.create_namespace(k8s_namespace)
            
            # 2. Deployment 생성
            resource_limits = {
                "limits": {
                    "cpu": template.resource_limits.get("cpu", "1000m"),
                    "memory": template.resource_limits.get("memory", "2Gi")
                },
                "requests": {
                    "cpu": template.resource_limits.get("cpu", "1000m"),
                    "memory": template.resource_limits.get("memory", "2Gi")
                }
            }
            
            await k8s_service.create_deployment(
                namespace=k8s_namespace,
                deployment_name=k8s_deployment_name,
                image=template.base_image,
                environment_vars=template.environment_variables or {},
                resource_limits=resource_limits
            )
            
            # 3. Service 생성
            service_port = template.exposed_ports[0] if template.exposed_ports else 8080
            await k8s_service.create_service(
                namespace=k8s_namespace,
                service_name=f"svc-{new_user.id}",
                deployment_name=k8s_deployment_name,
                port=service_port
            )
            
            # 4. Environment 상태 업데이트
            new_environment.status = EnvironmentStatus.CREATING
            new_environment.external_port = service_port
            new_environment.access_url = f"http://{k8s_namespace}.local:{service_port}"
            db.commit()
            db.refresh(new_environment)
            
            logger.info(f"Kubernetes resources created for environment {new_environment.id}")
            
        except Exception as k8s_error:
            logger.error(f"Failed to create Kubernetes resources: {str(k8s_error)}")
            # K8s 리소스 생성 실패 시 환경 상태를 ERROR로 업데이트
            new_environment.status = EnvironmentStatus.ERROR
            new_environment.status_message = f"K8s creation failed: {str(k8s_error)}"
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


