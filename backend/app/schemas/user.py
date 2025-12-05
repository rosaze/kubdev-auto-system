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


class UserCreateAdmin(BaseModel):
    """사용자 생성 스키마 (관계자)"""
    name: str = Field(..., min_length=1, max_length=255)
    current_user_id: int = Field(..., description="현재 로그인한 사용자 ID")
    role: UserRole = Field(default=UserRole.ADMIN, description="사용자 역할")
    # hashed_password(접속 코드)는 서버에서 자동 생성

class UserCreateAdminResponse(BaseModel):
    """사용자 생성 응답 스키마 (관계자)"""
    id: int
    name: str
    role: UserRole
    access_code: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UserCreateUser(BaseModel):
    """사용자 생성 스키마 (일반 사용자)"""
    name: str = Field(..., min_length=1, max_length=255)
    current_user_id: int = Field(..., description="현재 로그인한 사용자 ID")
    role: UserRole = Field(default=UserRole.USER, description="사용자 역할")
    # hashed_password(접속 코드)는 서버에서 자동 생성

class UserCreateUserResponse(BaseModel):
    """사용자 생성 응답 스키마 (일반 사용자)"""
    class UserData(BaseModel):
        id: int
        name: str
        role: UserRole
        access_code: str
        is_active: bool
        created_at: datetime
    
    class EnvironmentData(BaseModel):
        id: int
        template_id: int
        user_id: int
        status: str
        port: int
        cpu: int
        memory: int
    
    user: UserData
    environment: EnvironmentData


class UserLogin(BaseModel):
    """로그인 요청 스키마"""
    access_code: str = Field(..., min_length=5, max_length=5, description="접속 코드")

class UserLoginResponse(BaseModel):
    """로그인 응답 스키마"""
    class UserInfo(BaseModel):
        id: int
        name: str
        role: UserRole
        last_login: Optional[datetime]

        class Config:
            from_attributes = True
    
    user_info: UserInfo


class UserLogout(BaseModel):
    """로그아웃 요청 스키마"""
    user_id: int = Field(..., description="로그아웃할 사용자 ID")


class UserCreateWithEnvironment(BaseModel):
    """사용자 생성 + 환경 자동 생성 요청 스키마"""
    name: str = Field(..., min_length=1, max_length=255, description="사용자 이름")
    template_id: int = Field(..., description="사용할 템플릿 ID")


class UserCreateWithEnvironmentResponse(BaseModel):
    """사용자 생성 + 환경 자동 생성 응답 스키마"""
    user_id: int
    access_code: str
    environment_id: int
    environment_status: str
    message: str = "사용자 계정과 개발 환경이 생성되었습니다."
