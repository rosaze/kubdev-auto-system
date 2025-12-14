"""
Authentication API Endpoints (New)
user_id 기반 인증 API
"""
import structlog
from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session
from datetime import datetime

from app.core.database import get_db
from app.models.user import User
from app.schemas.user import (
    UserLogin,
    UserLoginResponse,
    UserLogout
)

router = APIRouter()
log = structlog.get_logger(__name__)


@router.post("/login", response_model=UserLoginResponse)
async def login(
    login_data: UserLogin,
    db: Session = Depends(get_db)
):
    """접속 코드로 로그인"""
    log.info("Login attempt", access_code=login_data.access_code)
    
    # 접속 코드로 사용자 찾기
    user = db.query(User).filter(User.hashed_password == login_data.access_code).first()
    
    if not user:
        log.warning("Login failed: invalid access code", access_code=login_data.access_code)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access code"
        )

    if not user.is_active:
        log.warning("Login failed: inactive user", access_code=login_data.access_code, user_id=user.id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )

    # 마지막 로그인 시간 업데이트
    user.last_login_at = datetime.utcnow()
    db.commit()
    db.refresh(user)

    log.info("Login successful", user_id=user.id, user_name=user.name)

    # 사용자 정보 반환
    user_info = UserLoginResponse.UserInfo(
        id=user.id,
        name=user.name,
        role=user.role,
        last_login=user.last_login_at
    )

    return UserLoginResponse(user_info=user_info)


@router.post("/logout")
async def logout(
    logout_data: UserLogout,
    db: Session = Depends(get_db)
):
    """사용자 로그아웃"""
    log.info("User logout requested", user_id=logout_data.user_id)

    # 사용자 존재 확인
    user = db.query(User).filter(User.id == logout_data.user_id).first()
    if not user:
        log.warning("Logout failed: user not found", user_id=logout_data.user_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    log.info("User logged out", user_id=user.id, user_name=user.name)

    return {"message": "로그아웃 성공"}


@router.get("/my-environment")
async def get_my_environment(
    db: Session = Depends(get_db)
):
    """현재 로그인한 사용자의 환경 정보 조회 (간단한 JWT 없이)"""
    from app.models.environment import EnvironmentInstance, EnvironmentStatus
    from app.services.kubernetes_service import KubernetesService
    from fastapi import Request

    # TODO: 임시 구현 - JWT 토큰 인증으로 개선 필요
    # 현재는 모든 사용자의 환경을 조회하는 방식으로 임시 구현

    log.info("My environment requested")

    try:
        # 가장 최근에 생성된 환경 조회 (임시)
        environment = db.query(EnvironmentInstance).order_by(
            EnvironmentInstance.created_at.desc()
        ).first()

        if not environment:
            log.warning("No environment found for any user")
            return {
                "status": "not_found",
                "can_access": False,
                "message": "환경이 생성되지 않았습니다. 관리자에게 문의하세요."
            }

        # 간단한 구현: DB의 access_url을 직접 사용
        access_url = environment.access_url
        can_access = (
            environment.status == EnvironmentStatus.RUNNING and
            access_url is not None
        )

        # 템플릿 정보 가져오기
        template = None
        template_info = {}
        if environment.template_id:
            from app.models.project_template import ProjectTemplate
            template = db.query(ProjectTemplate).filter(ProjectTemplate.id == environment.template_id).first()
            if template:
                template_info = {
                    "template_name": template.name,
                    "template_description": template.description,
                    "base_image": template.base_image,
                    "resource_limits": template.resource_limits or {},
                    "exposed_ports": template.exposed_ports or [],
                    "environment_variables": {k: v for k, v in (template.environment_variables or {}).items() if not any(secret in k.lower() for secret in ['password', 'secret', 'key', 'token'])},
                }

        log.info("Environment info retrieved",
                 environment_id=environment.id,
                 status=environment.status.value,
                 can_access=can_access)

        return {
            "status": "ready" if can_access else environment.status.value,
            "environment_id": environment.id,
            "environment_name": environment.name,
            "environment_status": environment.status.value,
            "access_url": access_url,
            "git_repository": environment.git_repository,
            "git_branch": environment.git_branch,
            "can_access": can_access,
            "started_at": environment.started_at.isoformat() if environment.started_at else None,
            "expires_at": environment.expires_at.isoformat() if environment.expires_at else None,
            "message": "환경이 준비되었습니다" if can_access else f"환경 상태: {environment.status.value}",
            **template_info
        }

    except Exception as e:
        log.error("Failed to get environment info", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get environment info: {str(e)}"
        )