"""
Security and Authentication utilities
보안 및 인증 관련 유틸리티
"""

from jose import jwt
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from passlib.context import CryptContext
from passlib.hash import bcrypt
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from .config import settings
from app.models.user import User

# 비밀번호 해싱 컨텍스트
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """비밀번호 검증"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """비밀번호 해싱"""
    return pwd_context.hash(password)


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """JWT 액세스 토큰 생성"""
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire, "iat": datetime.utcnow()})

    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    return encoded_jwt


def verify_access_token(token: str) -> Dict[str, Any]:
    """JWT 액세스 토큰 검증"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    """사용자 인증"""
    user = db.query(User).filter(User.email == email).first()

    if not user:
        return None

    if not verify_password(password, user.hashed_password):
        return None

    return user


def create_user_token(user: User) -> Dict[str, Any]:
    """사용자용 JWT 토큰 생성"""
    token_data = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role.value,
        "organization_id": user.organization_id,
        "team_id": user.team_id
    }

    access_token = create_access_token(data=token_data)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user_id": user.id,
        "email": user.email,
        "role": user.role.value
    }


def generate_api_key(user_id: int, description: str = "") -> str:
    """API 키 생성 (장기간 유효한 토큰)"""
    token_data = {
        "sub": str(user_id),
        "type": "api_key",
        "description": description,
        "iat": datetime.utcnow()
        # 만료시간 없음 (무기한)
    }

    api_key = jwt.encode(token_data, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    return api_key


def verify_api_key(api_key: str) -> Dict[str, Any]:
    """API 키 검증"""
    try:
        payload = jwt.decode(api_key, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])

        if payload.get("type") != "api_key":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key format"
            )

        return payload

    except jwt.JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )


def check_user_permissions(user: User, required_role: str = None, organization_id: int = None) -> bool:
    """사용자 권한 확인"""

    # 활성 사용자 체크
    if not user.is_active:
        return False

    # 역할 기반 권한 체크
    if required_role:
        user_role_hierarchy = {
            "super_admin": 4,
            "org_admin": 3,
            "team_leader": 2,
            "developer": 1
        }

        user_level = user_role_hierarchy.get(user.role.value, 0)
        required_level = user_role_hierarchy.get(required_role, 0)

        if user_level < required_level:
            return False

    # 조직 기반 권한 체크
    if organization_id and user.organization_id != organization_id:
        # super_admin은 모든 조직에 접근 가능
        if user.role.value != "super_admin":
            return False

    return True


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