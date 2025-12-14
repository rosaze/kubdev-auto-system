"""
Project Template Schemas
프로젝트 템플릿 관련 Pydantic 스키마
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from app.models.project_template import TemplateStatus


class ProjectTemplateBase(BaseModel):
    """프로젝트 템플릿 기본 스키마"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    version: str = Field(default="1.0.0", max_length=50)
    organization_id: Optional[int] = None


class ProjectTemplateCreate(ProjectTemplateBase):
    """프로젝트 템플릿 생성 스키마"""
    stack_config: Dict[str, Any] = Field(..., description="기술 스택 설정")
    dependencies: List[str] = Field(default=[], description="패키지 의존성 목록")
    base_image: str = Field(..., description="베이스 Docker 이미지")
    custom_dockerfile: Optional[str] = None
    init_scripts: List[str] = Field(default=[], description="초기화 스크립트")
    post_start_commands: List[str] = Field(default=[], description="시작 후 명령어")
    resource_limits: Dict[str, str] = Field(default={
        "cpu": "1000m",
        "memory": "2Gi",
        "storage": "10Gi"
    })
    exposed_ports: List[int] = Field(default=[8080], description="노출할 포트")
    environment_variables: Dict[str, str] = Field(default={}, description="환경 변수")
    default_git_repo: Optional[str] = None
    git_branch: str = Field(default="main")
    is_public: bool = Field(default=False)


class ProjectTemplateUpdate(BaseModel):
    """프로젝트 템플릿 업데이트 스키마"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    version: Optional[str] = Field(None, max_length=50)
    status: Optional[TemplateStatus] = None
    organization_id: Optional[int] = None
    stack_config: Optional[Dict[str, Any]] = None
    dependencies: Optional[List[str]] = None
    base_image: Optional[str] = None
    custom_dockerfile: Optional[str] = None
    init_scripts: Optional[List[str]] = None
    post_start_commands: Optional[List[str]] = None
    resource_limits: Optional[Dict[str, str]] = None
    exposed_ports: Optional[List[int]] = None
    environment_variables: Optional[Dict[str, str]] = None
    default_git_repo: Optional[str] = None
    git_branch: Optional[str] = None
    is_public: Optional[bool] = None


class ProjectTemplateResponse(ProjectTemplateBase):
    """프로젝트 템플릿 응답 스키마"""
    id: int
    status: TemplateStatus
    stack_config: Dict[str, Any]
    dependencies: List[str]
    base_image: str
    custom_dockerfile: Optional[str]
    init_scripts: List[str]
    post_start_commands: List[str]
    resource_limits: Dict[str, str]
    exposed_ports: List[int]
    environment_variables: Dict[str, str]
    default_git_repo: Optional[str]
    git_branch: str
    is_public: bool
    created_by: int
    organization_id: Optional[int]
    usage_count: int
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class ProjectTemplateListResponse(BaseModel):
    """프로젝트 템플릿 목록 응답 스키마"""
    templates: List[ProjectTemplateResponse]
    total: int
    page: int
    size: int


class TemplateValidationResult(BaseModel):
    """템플릿 유효성 검증 결과"""
    is_valid: bool
    errors: List[str] = []
    warnings: List[str] = []


class TemplateDeploymentTest(BaseModel):
    """템플릿 배포 테스트 결과"""
    success: bool
    deployment_time: float
    test_pod_name: Optional[str] = None
    error_message: Optional[str] = None
    logs: Optional[str] = None