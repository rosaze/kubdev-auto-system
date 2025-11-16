"""
FastAPI Dependencies (Simplified)
API 종속성 및 간단한 인증 미들웨어
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import Optional

from .database import get_db
from .security import get_current_user_simple, get_current_user as get_user
from app.models.user import User, UserRole

# Bearer Token 스키마
security = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """현재 사용자 조회 (간단한 인증)"""
    return get_user(credentials, db)


def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """활성 사용자만 허용"""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    return current_user


def require_role(required_role: UserRole):
    """특정 역할 이상의 사용자만 허용하는 의존성 (개발용에서는 항상 허용)"""
    def role_checker(current_user: User = Depends(get_current_active_user)) -> User:
        # 개발용에서는 모든 역할 허용
        return current_user

    return role_checker


def require_organization_access(organization_id: Optional[int] = None):
    """특정 조직에 대한 접근 권한이 있는 사용자만 허용 (개발용에서는 항상 허용)"""
    def org_checker(current_user: User = Depends(get_current_active_user)) -> User:
        # 개발용에서는 모든 조직 접근 허용
        return current_user

    return org_checker


# 역할별 의존성 생성 (개발용에서는 모두 같은 함수)
get_admin_user = get_current_user
get_team_leader = get_current_user
get_super_admin = get_current_user


def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """선택적 사용자 인증 (토큰이 없어도 OK)"""

    if not credentials:
        return None

    try:
        return get_current_user_simple(credentials, db)
    except Exception:
        return None