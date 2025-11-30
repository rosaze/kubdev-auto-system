"""
User Schemas
사용자 관련 Pydantic 스키마
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from app.models.user import UserRole


class UserBase(BaseModel):
    """사용자 기본 스키마"""
    name: str = Field(..., min_length=1, max_length=255)
    role: UserRole = UserRole.USER


class UserCreate(BaseModel):
    """사용자 생성 스키마 (관리자용)"""
    name: str = Field(..., min_length=1, max_length=255)
    role: UserRole = UserRole.USER
    # hashed_password(접속 코드)는 서버에서 자동 생성


class UserUpdate(BaseModel):
    """사용자 업데이트 스키마"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


class UserResponse(UserBase):
    """사용자 응답 스키마"""
    id: int
    is_active: bool
    created_at: datetime
    last_login_at: Optional[datetime]

    class Config:
        from_attributes = True


class UserLogin(BaseModel):
    """로그인 요청 스키마"""
    access_code: str = Field(..., min_length=5, max_length=5, pattern="^[A-Z]{5}$", description="접속 코드")
    
    # 참고: access_code가 DB의 hashed_password와 매칭됨


class UserTokenResponse(BaseModel):
    """토큰 응답 스키마"""
    access_token: str
    token_type: str = "bearer"
    user: UserResponse