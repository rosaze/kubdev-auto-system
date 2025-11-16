"""
Simplified Security for Development
개발용 간단한 보안 시스템
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from app.models.user import User

# 개발용 간단한 인증 설정
security = HTTPBearer(auto_error=False)

# 개발용 고정 API 키 (실제 운영에서는 사용 금지)
DEV_API_KEYS = {
    "admin-key-123": {"role": "super_admin", "user_id": 1, "email": "admin@kubdev.local"},
    "dev-key-456": {"role": "developer", "user_id": 2, "email": "dev@kubdev.local"},
    "test-key-789": {"role": "org_admin", "user_id": 3, "email": "test@kubdev.local"}
}


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """비밀번호 검증 (개발용 - 단순 문자열 비교)"""
    # 개발용: 해시된 비밀번호가 실제로는 평문이라고 가정하고 비교
    # 또는 간단한 "dev-password" 형태로 비교
    if hashed_password.startswith("dev-"):
        return plain_password == hashed_password[4:]  # "dev-" 제거 후 비교
    return plain_password == hashed_password


def get_password_hash(password: str) -> str:
    """비밀번호 해싱 (개발용 - 단순 문자열 처리)"""
    # 개발용: "dev-" 접두사를 추가해서 개발용임을 명시
    return f"dev-{password}"


def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    """사용자 인증 (간단화)"""
    user = db.query(User).filter(User.email == email).first()

    if not user:
        return None

    if not verify_password(password, user.hashed_password):
        return None

    return user


def create_user_token(user: User) -> Dict[str, Any]:
    """사용자용 간단한 토큰 생성 (JWT 대신 간단한 키 사용)"""
    # 개발용: 사용자 ID를 기반으로 간단한 토큰 생성
    simple_token = f"user-{user.id}-{user.email.split('@')[0]}"

    return {
        "access_token": simple_token,
        "token_type": "bearer",
        "expires_in": 86400,  # 24시간
        "user_id": user.id,
        "email": user.email,
        "role": user.role.value
    }


def get_current_user_simple(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """간단한 현재 사용자 조회 (개발용)"""

    # 인증 없이 허용 (개발 모드)
    if not credentials:
        # 기본 관리자 사용자 반환
        return create_dev_user()

    token = credentials.credentials

    # 개발용 고정 API 키 확인
    if token in DEV_API_KEYS:
        user_data = DEV_API_KEYS[token]
        return create_dev_user(
            user_id=user_data["user_id"],
            email=user_data["email"],
            role=user_data["role"]
        )

    # 간단한 사용자 토큰 확인 (user-{id}-{name} 형식)
    if token.startswith("user-"):
        try:
            parts = token.split("-")
            user_id = int(parts[1])
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                return user
        except (ValueError, IndexError):
            pass

    # 인증 실패시에도 기본 사용자 반환 (개발용)
    return create_dev_user()


def create_dev_user(user_id: int = 1, email: str = "dev@kubdev.local", role: str = "super_admin") -> User:
    """개발용 임시 사용자 객체 생성"""
    from app.models.user import UserRole

    # 메모리상 임시 User 객체 생성
    class DevUser:
        def __init__(self):
            self.id = user_id
            self.email = email
            self.name = "Development User"
            self.role = getattr(UserRole, role.upper(), UserRole.DEVELOPER)
            self.is_active = True
            self.is_verified = True
            self.organization_id = 1
            self.team_id = None
            self.created_at = datetime.utcnow()
            self.environments = []

    return DevUser()


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """현재 사용자 조회 (인증 필수) - 개발용에서는 항상 성공"""
    user = get_current_user_simple(credentials, db)
    if not user:
        # 개발 모드에서는 기본 사용자 반환
        return create_dev_user()
    return user


def get_admin_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """관리자 권한 확인 - 개발용에서는 항상 허용"""
    return current_user


def get_super_admin(
    current_user: User = Depends(get_current_user)
) -> User:
    """슈퍼 관리자 권한 확인 - 개발용에서는 항상 허용"""
    return current_user


def get_team_leader(
    current_user: User = Depends(get_current_user)
) -> User:
    """팀 리더 권한 확인 - 개발용에서는 항상 허용"""
    return current_user


def check_user_permissions(user: User, required_role: str = None, organization_id: int = None) -> bool:
    """사용자 권한 확인 - 개발용에서는 항상 허용"""
    return True


def generate_api_key(user_id: int, description: str = "") -> str:
    """개발용 간단한 API 키 생성"""
    return f"dev-{user_id}-{description.replace(' ', '-')}-{datetime.now().strftime('%Y%m%d')}"


def mask_sensitive_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """민감한 데이터 마스킹"""
    sensitive_fields = ["password", "secret_key", "api_key", "token"]

    masked_data = data.copy()

    for key, value in masked_data.items():
        if any(field in key.lower() for field in sensitive_fields):
            if isinstance(value, str) and len(value) > 4:
                masked_data[key] = value[:4] + "*" * (len(value) - 4)
            else:
                masked_data[key] = "***"

    return masked_data


# 개발용 편의 함수들
def get_dev_token(role: str = "super_admin") -> str:
    """개발용 토큰 빠른 생성"""
    if role == "super_admin":
        return "admin-key-123"
    elif role == "developer":
        return "dev-key-456"
    elif role == "org_admin":
        return "test-key-789"
    else:
        return "admin-key-123"