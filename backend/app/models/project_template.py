"""
Project Template Model
프로젝트 템플릿 모델
"""

from sqlalchemy import Column, String, Integer, DateTime, Boolean, ForeignKey, JSON, Text, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.core.database import Base


class TemplateStatus(enum.Enum):
    """템플릿 상태"""
    DRAFT = "draft"         # 작성 중
    ACTIVE = "active"       # 활성화
    INACTIVE = "inactive"   # 비활성화
    DEPRECATED = "deprecated"  # 사용 중단


class ProjectTemplate(Base):
    """프로젝트 템플릿 모델"""
    __tablename__ = "project_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)

    # 기본 정보
    version = Column(String(50), default="1.0.0")
    status = Column(Enum(TemplateStatus), default=TemplateStatus.DRAFT)

    # 기술 스택 설정
    stack_config = Column(JSON, nullable=False)  # 언어, 프레임워크 등
    dependencies = Column(JSON, default=[])      # 패키지 의존성

    # Docker 이미지 설정
    base_image = Column(String(255), nullable=False)  # 베이스 IDE 이미지
    custom_dockerfile = Column(Text, nullable=True)    # 커스텀 Dockerfile

    # 초기화 스크립트
    init_scripts = Column(JSON, default=[])      # 환경 초기화 스크립트
    post_start_commands = Column(JSON, default=[])  # 시작 후 실행할 명령어

    # 리소스 제한
    resource_limits = Column(JSON, default={     # CPU, 메모리, 스토리지 제한
        "cpu": "1000m",
        "memory": "2Gi",
        "storage": "10Gi"
    })

    # 네트워크 설정
    exposed_ports = Column(JSON, default=[])     # 노출할 포트 목록
    environment_variables = Column(JSON, default={})  # 환경 변수

    # Git 설정
    default_git_repo = Column(String(500), nullable=True)  # 기본 Git 저장소
    git_branch = Column(String(100), default="main")       # 기본 브랜치

    # 접근 권한
    is_public = Column(Boolean, default=False)   # 공개 템플릿 여부

    # 생성자 정보
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    organization_id = Column(Integer, nullable=True, index=True)  # 조직 ID

    # 사용 통계
    usage_count = Column(Integer, default=0)     # 사용된 횟수

    # 타임스탬프
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # 관계
    creator = relationship("User")
    environments = relationship("EnvironmentInstance", back_populates="template")

    def __repr__(self):
        return f"<ProjectTemplate(name='{self.name}', version='{self.version}', status='{self.status.value}')>"