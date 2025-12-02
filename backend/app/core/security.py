"""
Simplified Security for Development
개발용 간단한 보안 시스템
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import secrets
import string
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
    "admin-key-123": {"role": "admin", "user_id": 1, "access_code": "ADMIN"},
    "user-key-456": {"role": "user", "user_id": 2, "access_code": "USER1"}
}


def generate_access_code(length: int = 5) -> str:
    """5자리 접속 코드 자동 생성 (영문 대문자 + 숫자)"""
    characters = string.ascii_uppercase + string.digits  # A-Z, 0-9
    return ''.join(secrets.choice(characters) for _ in range(length))


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


def authenticate_user(db: Session, access_code: str) -> Optional[User]:
    """사용자 인증 (접속 코드 기반)"""
    # hashed_password 필드가 실제로는 접속 코드를 저장함 (개발 중이므로 암호화 없이)
    user = db.query(User).filter(User.hashed_password == access_code.upper()).first()
    
    if not user:
        return None
    
    if not user.is_active:
        return None
    
    return user


def create_user_token(user: User) -> Dict[str, Any]:
    """사용자용 간단한 토큰 생성 (JWT 대신 간단한 키 사용)"""
    # 개발용: 접속 코드를 기반으로 간단한 토큰 생성
    simple_token = f"{user.id}-{user.hashed_password}"

    return {
        "access_token": simple_token,
        "token_type": "bearer",
        "expires_in": 86400,  # 24시간
        "user_id": user.id,
        "access_code": user.hashed_password,
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
            access_code=user_data["access_code"],
            role=user_data["role"]
        )

    # 간단한 사용자 토큰 확인 ({id}-{access_code} 형식)
    try:
        parts = token.split("-")
        if len(parts) >= 2:
            user_id = int(parts[0])
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                return user
    except (ValueError, IndexError):
        pass

    # 인증 실패시에도 기본 사용자 반환 (개발용)
    return create_dev_user()


def create_dev_user(user_id: int = 1, access_code: str = "ADMIN", role: str = "admin") -> User:
    """개발용 임시 사용자 객체 생성"""
    from app.models.user import UserRole

    # 메모리상 임시 User 객체 생성
    class DevUser:
        def __init__(self):
            self.id = user_id
            self.hashed_password = access_code  # 접속 코드
            self.name = "Development User"
            self.role = getattr(UserRole, role.upper(), UserRole.USER)
            self.is_active = True
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


def check_user_permissions(user: User, required_role: str = None) -> bool:
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
def get_dev_token(role: str = "admin") -> str:
    """개발용 토큰 빠른 생성"""
    if role == "admin":
        return "admin-key-123"
    else:
        return "user-key-456"