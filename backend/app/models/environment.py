"""
Environment Instance Model
개발 환경 인스턴스 모델
"""

from sqlalchemy import Column, String, Integer, DateTime, Boolean, ForeignKey, JSON, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.core.database import Base


class EnvironmentStatus(enum.Enum):
    """환경 상태"""
    PENDING = "pending"       # 생성 대기
    CREATING = "creating"     # 생성 중
    RUNNING = "running"       # 실행 중
    STOPPING = "stopping"     # 중지 중
    STOPPED = "stopped"       # 중지됨
    ERROR = "error"           # 오류
    EXPIRED = "expired"       # 만료됨


class EnvironmentInstance(Base):
    """개발 환경 인스턴스 모델"""
    __tablename__ = "environment_instances"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)  # 환경 이름 (사용자 정의)

    # 템플릿 및 사용자 연결
    template_id = Column(Integer, ForeignKey("project_templates.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # K8s 관련 정보
    k8s_namespace = Column(String(100), nullable=False)  # K8s 네임스페이스
    k8s_deployment_name = Column(String(100), nullable=False)  # Deployment 이름
    k8s_service_name = Column(String(100), nullable=True)     # Service 이름
    k8s_ingress_name = Column(String(100), nullable=True)     # Ingress 이름

    # 상태 관리
    status = Column(Enum(EnvironmentStatus), default=EnvironmentStatus.PENDING)
    status_message = Column(String(500), nullable=True)  # 상태 메시지

    # 접속 정보
    access_url = Column(String(500), nullable=True)      # IDE 접속 URL
    internal_ip = Column(String(50), nullable=True)      # 내부 IP
    external_port = Column(Integer, nullable=True)       # 외부 포트

    # Git 정보
    git_repository = Column(String(500), nullable=True)  # 클론된 Git 저장소
    git_branch = Column(String(100), nullable=True)      # 사용된 브랜치
    git_commit_hash = Column(String(100), nullable=True) # 커밋 해시

    # 리소스 사용량 (실시간 업데이트)
    current_resource_usage = Column(JSON, default={
        "cpu_usage": 0,
        "memory_usage": 0,
        "storage_usage": 0
    })

    # 환경 설정
    environment_config = Column(JSON, default={})        # 런타임 환경 설정
    port_mappings = Column(JSON, default=[])             # 포트 매핑 정보

    # 수명 관리
    expires_at = Column(DateTime(timezone=True), nullable=True)  # 만료 시간
    auto_stop_enabled = Column(Boolean, default=True)    # 자동 중지 여부
    last_accessed_at = Column(DateTime(timezone=True), nullable=True)  # 마지막 접속 시간

    # 타임스탬프
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)  # 시작 시간
    stopped_at = Column(DateTime(timezone=True), nullable=True)  # 중지 시간

    # 관계
    template = relationship("ProjectTemplate", back_populates="environments")
    user = relationship("User", back_populates="environments")
    resource_metrics = relationship("ResourceMetric", back_populates="environment")

    def __repr__(self):
        return f"<EnvironmentInstance(name='{self.name}', status='{self.status.value}', user='{self.user.name}')>"