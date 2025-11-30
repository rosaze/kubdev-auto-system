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
    SUPER_ADMIN = "super_admin"  # 플랫폼 관리자
    ORG_ADMIN = "org_admin"      # 조직 관리자
    TEAM_LEADER = "team_leader"   # 팀 리더
    DEVELOPER = "developer"       # 개발자


class User(Base):
    """사용자 모델"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    hashed_password = Column(String(255), unique=True, index=True, nullable=False)  # 접속 코드 (개발 중이므로 암호화 없이 저장)

    # 권한 관리
    role = Column(Enum(UserRole), default=UserRole.DEVELOPER, nullable=False)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)

    # 조직/팀 연결
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True)

    # 타임스탬프
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    # 관계
    organization = relationship("Organization", back_populates="users")
    team = relationship("Team", back_populates="users")
    environments = relationship("EnvironmentInstance", back_populates="user")

    def __repr__(self):
        return f"<User(code='{self.hashed_password}', name='{self.name}', role='{self.role.value}')>"