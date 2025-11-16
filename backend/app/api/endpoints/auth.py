"""
Authentication API Endpoints
인증 및 사용자 관리 API
"""

from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session
from datetime import datetime

from app.core.database import get_db
from app.core.security import (
    authenticate_user,
    create_user_token,
    get_password_hash,
    generate_api_key
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


@router.post("/login", response_model=UserTokenResponse)
async def login(
    login_data: UserLogin,
    db: Session = Depends(get_db)
):
    """사용자 로그인"""

    user = authenticate_user(db, login_data.email, login_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )

    # 마지막 로그인 시간 업데이트
    user.last_login_at = datetime.utcnow()
    db.commit()

    # JWT 토큰 생성
    token_data = create_user_token(user)

    return UserTokenResponse(
        access_token=token_data["access_token"],
        token_type=token_data["token_type"],
        user=user
    )


@router.post("/register", response_model=UserResponse)
async def register(
    user_data: UserCreate,
    db: Session = Depends(get_db)
):
    """새 사용자 등록"""

    # 이메일 중복 체크
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # 조직 존재 확인
    if user_data.organization_id:
        organization = db.query(Organization).filter(
            Organization.id == user_data.organization_id
        ).first()
        if not organization:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found"
            )

    # 팀 존재 확인
    if user_data.team_id:
        team = db.query(Team).filter(Team.id == user_data.team_id).first()
        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team not found"
            )

    try:
        # 사용자 생성
        hashed_password = get_password_hash(user_data.password)

        user = User(
            email=user_data.email,
            name=user_data.name,
            hashed_password=hashed_password,
            role=user_data.role,
            organization_id=user_data.organization_id,
            team_id=user_data.team_id
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        return user

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create user: {str(e)}"
        )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """현재 사용자 정보 조회"""
    return current_user


@router.patch("/me", response_model=UserResponse)
async def update_current_user(
    user_update: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """현재 사용자 정보 수정"""

    try:
        # 본인은 역할 변경 불가
        update_data = user_update.dict(exclude_unset=True, exclude={"role"})

        # 팀 변경 시 존재 확인
        if "team_id" in update_data and update_data["team_id"]:
            team = db.query(Team).filter(Team.id == update_data["team_id"]).first()
            if not team:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Team not found"
                )

        # 업데이트 적용
        for field, value in update_data.items():
            setattr(current_user, field, value)

        db.commit()
        db.refresh(current_user)

        return current_user

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update user: {str(e)}"
        )


@router.post("/logout")
async def logout(current_user: User = Depends(get_current_user)):
    """사용자 로그아웃 (클라이언트에서 토큰 삭제)"""
    # JWT는 stateless이므로 서버에서 할 일은 없음
    # 클라이언트에서 토큰을 삭제하면 됨
    return {"message": "Successfully logged out"}


@router.post("/api-keys")
async def create_api_key(
    description: str,
    current_user: User = Depends(get_current_user)
):
    """API 키 생성"""

    try:
        api_key = generate_api_key(current_user.id, description)

        return {
            "api_key": api_key,
            "description": description,
            "user_id": current_user.id,
            "created_at": datetime.utcnow().isoformat(),
            "warning": "이 API 키를 안전한 곳에 저장하세요. 다시 보여드리지 않습니다."
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create API key: {str(e)}"
        )


# Admin 전용 엔드포인트
@router.get("/users", response_model=list[UserResponse])
async def list_users(
    organization_id: int = None,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """모든 사용자 목록 (Admin 전용)"""

    query = db.query(User)

    # 조직 필터링
    if organization_id:
        query = query.filter(User.organization_id == organization_id)

    # org_admin은 자신의 조직만, super_admin은 모든 조직
    if admin_user.role == UserRole.ORG_ADMIN:
        query = query.filter(User.organization_id == admin_user.organization_id)

    users = query.all()
    return users


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user_admin(
    user_id: int,
    user_update: UserUpdate,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """사용자 정보 수정 (Admin 전용)"""

    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # 권한 체크: org_admin은 자신의 조직 사용자만 수정 가능
    if admin_user.role == UserRole.ORG_ADMIN:
        if target_user.organization_id != admin_user.organization_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No permission to modify this user"
            )

    try:
        update_data = user_update.dict(exclude_unset=True)

        # 역할 변경 체크
        if "role" in update_data:
            new_role = update_data["role"]

            # org_admin은 super_admin 역할을 부여할 수 없음
            if admin_user.role == UserRole.ORG_ADMIN and new_role == UserRole.SUPER_ADMIN:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Cannot assign super_admin role"
                )

        # 업데이트 적용
        for field, value in update_data.items():
            setattr(target_user, field, value)

        db.commit()
        db.refresh(target_user)

        return target_user

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
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

    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # 본인 삭제 방지
    if target_user.id == admin_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete yourself"
        )

    # 권한 체크
    if admin_user.role == UserRole.ORG_ADMIN:
        if target_user.organization_id != admin_user.organization_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No permission to delete this user"
            )

    # 활성 환경이 있는지 체크
    from app.models.environment import EnvironmentInstance
    active_environments = db.query(EnvironmentInstance).filter(
        EnvironmentInstance.user_id == user_id,
        EnvironmentInstance.status.in_(['running', 'pending', 'creating'])
    ).count()

    if active_environments > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete user: {active_environments} active environments exist"
        )

    try:
        # 사용자 비활성화 (완전 삭제 대신)
        target_user.is_active = False
        db.commit()

        return {"message": "User deactivated successfully"}

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete user: {str(e)}"
        )