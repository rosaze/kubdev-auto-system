"""
User Model
사용자 정보 모델
"""

from sqlalchemy import Column, String, Integer, DateTime, Boolean, ForeignKey, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.core.database import Base


class UserRole(enum.Enum):
    """사용자 역할"""
    ADMIN = "admin"  # 관리자
    USER = "user"    # 일반 사용자


class User(Base):
    """사용자 모델"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    hashed_password = Column(String(255), unique=True, index=True, nullable=False)  # 접속 코드 (개발 중이므로 암호화 없이 저장)

    # 권한 관리
    role = Column(Enum(UserRole), default=UserRole.USER, nullable=False)
    is_active = Column(Boolean, default=True)

    # 타임스탬프
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    # 관계
    environments = relationship("EnvironmentInstance", back_populates="user")

    def __repr__(self):
        return f"<User(code='{self.hashed_password}', name='{self.name}', role='{self.role.value}')>"