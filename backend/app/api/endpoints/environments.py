"""
Environment API Endpoints
개발 환경 관리 API
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
import uuid

from app.core.database import get_db
from app.models.environment import EnvironmentInstance, EnvironmentStatus
from app.models.project_template import ProjectTemplate
from app.models.user import User
from app.schemas.environment import (
    EnvironmentCreate,
    EnvironmentResponse,
    EnvironmentUpdate,
    EnvironmentActionRequest,
    EnvironmentListResponse
)
from app.services.kubernetes_service import KubernetesService
from app.services.environment_service import EnvironmentService
from app.core.dependencies import get_current_user

router = APIRouter()


@router.post("/", response_model=EnvironmentResponse)
async def create_environment(
    environment_data: EnvironmentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """새로운 개발 환경 생성"""

    # 템플릿 존재 확인
    template = db.query(ProjectTemplate).filter(
        ProjectTemplate.id == environment_data.template_id
    ).first()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # 현재 사용자 사용
    user = current_user

    try:
        # 고유한 환경 이름 생성
        unique_id = str(uuid.uuid4())[:8]
        k8s_name = f"{environment_data.name}-{unique_id}".lower()

        # 환경 인스턴스 생성
        environment = EnvironmentInstance(
            name=environment_data.name,
            template_id=environment_data.template_id,
            user_id=current_user.id,
            k8s_namespace="kubdev",  # 기본 네임스페이스
            k8s_deployment_name=f"env-{k8s_name}",
            k8s_service_name=f"svc-{k8s_name}",
            git_repository=environment_data.git_repository,
            git_branch=environment_data.git_branch or "main",
            status=EnvironmentStatus.CREATING,
            expires_at=environment_data.expires_at
        )

        db.add(environment)
        db.commit()
        db.refresh(environment)

        # K8s에 환경 배포 (백그라운드 작업)
        env_service = EnvironmentService(db)
        await env_service.deploy_environment(environment.id)

        return environment

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create environment: {str(e)}")


@router.get("/", response_model=EnvironmentListResponse)
async def list_environments(
    user_id: Optional[int] = Query(None, description="Filter by user ID"),
    status: Optional[EnvironmentStatus] = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(10, ge=1, le=100, description="Page size"),
    db: Session = Depends(get_db)
):
    """환경 목록 조회"""

    query = db.query(EnvironmentInstance)

    # 필터링
    if user_id:
        query = query.filter(EnvironmentInstance.user_id == user_id)
    if status:
        query = query.filter(EnvironmentInstance.status == status)

    # 전체 개수
    total = query.count()

    # 페이징
    offset = (page - 1) * size
    environments = query.offset(offset).limit(size).all()

    return EnvironmentListResponse(
        environments=environments,
        total=total,
        page=page,
        size=size
    )


@router.get("/{environment_id}", response_model=EnvironmentResponse)
async def get_environment(
    environment_id: int,
    db: Session = Depends(get_db)
):
    """특정 환경 조회"""

    environment = db.query(EnvironmentInstance).filter(
        EnvironmentInstance.id == environment_id
    ).first()

    if not environment:
        raise HTTPException(status_code=404, detail="Environment not found")

    return environment


@router.patch("/{environment_id}", response_model=EnvironmentResponse)
async def update_environment(
    environment_id: int,
    update_data: EnvironmentUpdate,
    db: Session = Depends(get_db)
):
    """환경 정보 업데이트"""

    environment = db.query(EnvironmentInstance).filter(
        EnvironmentInstance.id == environment_id
    ).first()

    if not environment:
        raise HTTPException(status_code=404, detail="Environment not found")

    # 업데이트 적용
    update_dict = update_data.dict(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(environment, field, value)

    db.commit()
    db.refresh(environment)

    return environment


@router.post("/{environment_id}/actions")
async def environment_action(
    environment_id: int,
    action_request: EnvironmentActionRequest,
    db: Session = Depends(get_db)
):
    """환경 액션 실행 (start, stop, restart, delete)"""

    environment = db.query(EnvironmentInstance).filter(
        EnvironmentInstance.id == environment_id
    ).first()

    if not environment:
        raise HTTPException(status_code=404, detail="Environment not found")

    env_service = EnvironmentService(db)

    try:
        if action_request.action == "start":
            await env_service.start_environment(environment_id)
        elif action_request.action == "stop":
            await env_service.stop_environment(environment_id)
        elif action_request.action == "restart":
            await env_service.restart_environment(environment_id)
        elif action_request.action == "delete":
            await env_service.delete_environment(environment_id)
        else:
            raise HTTPException(status_code=400, detail="Invalid action")

        return {"message": f"Action '{action_request.action}' executed successfully"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Action failed: {str(e)}")


@router.get("/{environment_id}/logs")
async def get_environment_logs(
    environment_id: int,
    tail_lines: int = Query(100, ge=1, le=1000, description="Number of log lines to retrieve"),
    db: Session = Depends(get_db)
):
    """환경 로그 조회"""

    environment = db.query(EnvironmentInstance).filter(
        EnvironmentInstance.id == environment_id
    ).first()

    if not environment:
        raise HTTPException(status_code=404, detail="Environment not found")

    try:
        k8s_service = KubernetesService()
        logs = await k8s_service.get_pod_logs(
            namespace=environment.k8s_namespace,
            deployment_name=environment.k8s_deployment_name,
            tail_lines=tail_lines
        )

        return {"logs": logs}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve logs: {str(e)}")


@router.get("/{environment_id}/access-info")
async def get_access_info(
    environment_id: int,
    db: Session = Depends(get_db)
):
    """환경 접속 정보 조회"""

    environment = db.query(EnvironmentInstance).filter(
        EnvironmentInstance.id == environment_id
    ).first()

    if not environment:
        raise HTTPException(status_code=404, detail="Environment not found")

    if environment.status != EnvironmentStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Environment is not running")

    return {
        "environment_id": environment.id,
        "access_url": environment.access_url,
        "status": environment.status.value,
        "ports": environment.port_mappings
    }