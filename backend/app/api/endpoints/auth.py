"""
Authentication API Endpoints
인증 및 사용자 관리 API
"""
import structlog
from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session
from datetime import datetime

from app.core.database import get_db
from app.core.security import (
    authenticate_user,
    create_user_token,
    generate_api_key,
    generate_access_code
)
from app.core.dependencies import get_current_user, get_admin_user
from app.models.user import User, UserRole
from app.models.organization import Organization, Team
from app.schemas.user import (
    UserCreate,
    UserResponse,
    UserUpdate,
    UserLogin,
    UserTokenResponse
)

router = APIRouter()
log = structlog.get_logger(__name__)


@router.post("/login", response_model=UserTokenResponse)
async def login(
    login_data: UserLogin,
    db: Session = Depends(get_db)
):
    """접속 코드로 로그인"""
    log.info("Login attempt", access_code=login_data.access_code)
    user = authenticate_user(db, login_data.access_code)
    if not user:
        log.warning("Login failed: invalid access code", access_code=login_data.access_code)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access code",
            headers={"WWW-Authenticate": "Bearer"},
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

    # JWT 토큰 생성
    token_data = create_user_token(user)
    log.info("Login successful", user_id=user.id, access_code=user.hashed_password)

    return UserTokenResponse(
        access_token=token_data["access_token"],
        token_type=token_data["token_type"],
        role=user.role,
        user_id=user.id,
        name=user.name
    )


@router.post("/create-user", response_model=UserResponse)
async def create_user(
    user_data: UserCreate,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """새 사용자 생성 (관리자 전용)"""
    log.info("User creation attempt by admin", admin_id=admin_user.id, new_user_name=user_data.name)
    
    # 접속 코드 자동 생성 (중복 확인)
    max_attempts = 10
    access_code = None
    for _ in range(max_attempts):
        temp_code = generate_access_code()
        existing = db.query(User).filter(User.hashed_password == temp_code).first()
        if not existing:
            access_code = temp_code
            break
    
    if not access_code:
        log.error("Failed to generate unique access code")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate unique access code"
        )

    try:
        # 사용자 생성
        user = User(
            name=user_data.name,
            hashed_password=access_code,  # 접속 코드를 hashed_password에 저장 (암호화 없이)
            role=user_data.role,
            is_active=True
        )

        db.add(user)
        db.commit()
        db.refresh(user)
        log.info("User created successfully", user_id=user.id, access_code=access_code, created_by=admin_user.id)
        return user

    except Exception as e:
        db.rollback()
        log.error("User creation failed: internal server error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create user: {str(e)}"
        )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """현재 사용자 정보 조회"""
    log.info("Fetching current user info", user_id=current_user.id)
    return current_user


@router.patch("/me", response_model=UserResponse)
async def update_current_user(
    user_update: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """현재 사용자 정보 수정"""
    log.info("Updating current user", user_id=current_user.id, update_data=user_update.dict(exclude_unset=True))
    try:
        # 본인은 역할 변경 불가
        update_data = user_update.dict(exclude_unset=True, exclude={"role"})

        # 업데이트 적용
        for field, value in update_data.items():
            setattr(current_user, field, value)

        db.commit()
        db.refresh(current_user)
        log.info("User updated successfully", user_id=current_user.id)
        return current_user

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        log.error("User update failed: internal server error", user_id=current_user.id, error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update user: {str(e)}"
        )


@router.post("/logout")
async def logout(current_user: User = Depends(get_current_user)):
    """사용자 로그아웃 (클라이언트에서 토큰 삭제)"""
    log.info("User logged out", user_id=current_user.id)
    # JWT는 stateless이므로 서버에서 할 일은 없음
    # 클라이언트에서 토큰을 삭제하면 됨
    return {"message": "Successfully logged out"}


@router.post("/api-keys")
async def create_api_key(
    description: str,
    current_user: User = Depends(get_current_user)
):
    """API 키 생성"""
    log.info("Creating API key", user_id=current_user.id, description=description)
    try:
        api_key = generate_api_key(current_user.id, description)
        log.info("API key created successfully", user_id=current_user.id)
        return {
            "api_key": api_key,
            "description": description,
            "user_id": current_user.id,
            "created_at": datetime.utcnow().isoformat(),
            "warning": "이 API 키를 안전한 곳에 저장하세요. 다시 보여드리지 않습니다."
        }

    except Exception as e:
        log.error("API key creation failed", user_id=current_user.id, error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create API key: {str(e)}"
        )


# Admin 전용 엔드포인트
@router.get("/users", response_model=list[UserResponse])
async def list_users(
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """모든 사용자 목록 (Admin 전용)"""
    log.info("Admin listing users", admin_id=admin_user.id)
    users = db.query(User).all()
    log.info("Found users", count=len(users))
    return users


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user_admin(
    user_id: int,
    user_update: UserUpdate,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """사용자 정보 수정 (Admin 전용)"""
    log.info("Admin updating user", admin_id=admin_user.id, target_user_id=user_id)
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        log.warning("Admin user update failed: user not found", target_user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    try:
        update_data = user_update.dict(exclude_unset=True)

        # 업데이트 적용
        for field, value in update_data.items():
            setattr(target_user, field, value)

        db.commit()
        db.refresh(target_user)
        log.info("Admin user update successful", admin_id=admin_user.id, target_user_id=user_id)
        return target_user

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        log.error("Admin user update failed: internal server error", admin_id=admin_user.id, target_user_id=user_id, error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update user: {str(e)}"
        )


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """사용자 삭제 (Admin 전용)"""
    log.info("Admin deleting user", admin_id=admin_user.id, target_user_id=user_id)
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        log.warning("Admin user delete failed: user not found", target_user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # 본인 삭제 방지
    if target_user.id == admin_user.id:
        log.warning("Admin user delete failed: cannot delete self", admin_id=admin_user.id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete yourself"
        )

    # 활성 환경이 있는지 체크
    from app.models.environment import EnvironmentInstance
    active_environments = db.query(EnvironmentInstance).filter(
        EnvironmentInstance.user_id == user_id,
        EnvironmentInstance.status.in_(['running', 'pending', 'creating'])
    ).count()

    if active_environments > 0:
        log.warning("Admin user delete failed: user has active environments", target_user_id=user_id, active_env_count=active_environments)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete user: {active_environments} active environments exist"
        )

    try:
        # 사용자 비활성화 (완전 삭제 대신)
        target_user.is_active = False
        db.commit()
        log.info("User deactivated successfully", target_user_id=user_id)
        return {"message": "User deactivated successfully"}

    except Exception as e:
        db.rollback()
        log.error("Admin user delete failed: internal server error", admin_id=admin_user.id, target_user_id=user_id, error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete user: {str(e)}"
        )