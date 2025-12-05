"""
Environment API Endpoints
개발 환경 관리 API
"""
import structlog
from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
import uuid
import yaml

from app.core.database import get_db
from app.models.environment import EnvironmentInstance, EnvironmentStatus
from app.models.project_template import ProjectTemplate
from app.models.user import User
from app.schemas.environment import (
    EnvironmentResponse,
    EnvironmentUpdate,
    EnvironmentActionRequest,
    EnvironmentListResponse
)
from app.services.kubernetes_service import KubernetesService
from app.services.environment_service import EnvironmentService
from app.core.dependencies import get_current_user

router = APIRouter()
log = structlog.get_logger(__name__)


@router.post("/create-from-yaml", response_model=Dict[str, Any])
async def create_environment_from_yaml(
    template_id: int = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    새로운 개발 환경을 KubeDevEnvironment CRD YAML 파일을 통해 생성합니다.
    """
    log.info("Creating new environment from YAML", user_id=current_user.id, filename=file.filename, template_id=template_id)

    # 0. Check if template exists
    template = db.query(ProjectTemplate).filter(ProjectTemplate.id == template_id).first()
    if not template:
        log.warning("Template not found", template_id=template_id)
        raise HTTPException(status_code=404, detail=f"ProjectTemplate with id {template_id} not found.")

    if not file.filename.lower().endswith(('.yaml', '.yml')):
        raise HTTPException(status_code=400, detail="Invalid file type. Only .yaml or .yml files are accepted.")

    # 1. Read and decode YAML file
    yaml_bytes = await file.read()
    yaml_string = ""
    try:
        yaml_string = yaml_bytes.decode("utf-8")
    except UnicodeDecodeError:
        try:
            yaml_string = yaml_bytes.decode("cp949")
            log.info("Decoded YAML file using cp949 encoding as a fallback.")
        except UnicodeDecodeError:
            log.error("Failed to decode YAML file with both utf-8 and cp949.", exc_info=True)
            raise HTTPException(
                status_code=400,
                detail="Could not decode file. Please ensure it is saved with UTF-8 or CP949 encoding."
            )

    # 2. Parse and validate YAML
    try:
        custom_object = yaml.safe_load(yaml_string)
        if not isinstance(custom_object, dict):
            raise HTTPException(status_code=400, detail="Invalid YAML format: not a dictionary.")

        api_version = custom_object.get("apiVersion")
        kind = custom_object.get("kind")
        if api_version != "kubedev.my-project.com/v1alpha1" or kind != "KubeDevEnvironment":
            raise HTTPException(status_code=400, detail="Invalid YAML: apiVersion or kind does not match KubeDevEnvironment CRD.")

        # Inject/overwrite userName from the authenticated user for security
        if "spec" not in custom_object: custom_object["spec"] = {}
        custom_object["spec"]["userName"] = current_user.name
        log.info(f"Injected/overwrote userName '{current_user.name}' into CRD spec.")

    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"YAML parsing error: {str(e)}")

    # 3. Apply the Custom Resource to Kubernetes
    try:
        k8s_service = KubernetesService()
        api_response = await k8s_service.create_custom_object(custom_object)
        log.info("Successfully applied KubeDevEnvironment CRD to Kubernetes.", crd_name=custom_object.get("metadata", {}).get("name"))
        
        # CRD를 생성한 후, 우리 시스템에서 환경을 추적하기 위해 DB에 레코드를 생성합니다.
        env_name = custom_object.get("metadata", {}).get("name")
        environment = EnvironmentInstance(
            name=env_name,
            template_id=template_id,
            user_id=current_user.id,
            k8s_namespace=custom_object.get("metadata", {}).get("namespace", "default"),
            k8s_deployment_name=env_name, # CRD 이름과 동일하게 설정 (컨트롤러의 규칙에 따라 달라질 수 있음)
            status=EnvironmentStatus.CREATING,
            git_repository=custom_object.get("spec", {}).get("gitRepository")
        )
        db.add(environment)
        db.commit()
        db.refresh(environment)
        log.info("Environment DB instance created for tracking.", environment_id=environment.id)

        # 복잡한 k8s 응답 객체 대신 명확한 성공 메시지를 직접 만들어 반환합니다.
        return {
            "status": "success",
            "message": "KubeDevEnvironment custom resource created successfully.",
            "crd_name": custom_object.get("metadata", {}).get("name"),
            "namespace": custom_object.get("metadata", {}).get("namespace", "default")
        }
    except Exception as e:
        log.error("Failed to apply CRD to Kubernetes or create DB record", error=str(e), exc_info=True)
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
    log.info("Listing environments", user_id=user_id, status=status, page=page, size=size)
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

    # IDE URL 동적 생성 (Kubernetes API로 실제 접속 가능한 주소 생성)
    k8s_service = KubernetesService()
    for env in environments:
        if env.status == EnvironmentStatus.RUNNING:
            try:
                # CRD status에서 ideUrl 읽기
                crd_name = env.k8s_deployment_name
                crd_namespace = env.k8s_namespace

                try:
                    custom_obj = await k8s_service.get_custom_object(
                        "kubedev.my-project.com", "v1alpha1", crd_namespace, "kubedevenvironments", crd_name
                    )
                    ide_url = custom_obj.get("status", {}).get("ideUrl")
                    log.info("Retrieved IDE URL from CRD", env_id=env.id, ide_url=ide_url)

                    # ideUrl이 비어있거나 .local 도메인인 경우 NodePort URL 생성
                    if not ide_url or ".local" in ide_url:
                        log.info("Attempting to generate NodePort URL", env_id=env.id)
                        # 서비스 이름은 Controller가 "ide-<crd-name>" 형식으로 생성
                        service_name = f"ide-{crd_name}"
                        # CRD status에서 실제 namespace 가져오기
                        actual_namespace = custom_obj.get("status", {}).get("namespace") or crd_namespace
                        log.info("Service info", service=service_name, namespace=actual_namespace)

                        # Kubernetes API로 NodePort URL 가져오기
                        nodeport_url = await k8s_service.get_nodeport_url(service_name, actual_namespace)
                        log.info("NodePort URL result", env_id=env.id, url=nodeport_url)
                        if nodeport_url:
                            env.access_url = nodeport_url
                        elif ide_url:
                            # fallback to original ideUrl if present
                            env.access_url = ide_url
                    else:
                        env.access_url = ide_url
                except Exception as e:
                    log.warning("Failed to get IDE URL from CRD", env_id=env.id, error=str(e))
            except Exception as e:
                log.warning("Failed to generate access URL", env_id=env.id, error=str(e))

    log.info("Found environments", total=total, page_count=len(environments))
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
    log.info("Getting environment details", environment_id=environment_id)
    environment = db.query(EnvironmentInstance).filter(
        EnvironmentInstance.id == environment_id
    ).first()

    if not environment:
        log.warning("Get environment failed: not found", environment_id=environment_id)
        raise HTTPException(status_code=404, detail="Environment not found")

    return environment


@router.patch("/{environment_id}", response_model=EnvironmentResponse)
async def update_environment(
    environment_id: int,
    update_data: EnvironmentUpdate,
    db: Session = Depends(get_db)
):
    """환경 정보 업데이트"""
    log.info("Updating environment", environment_id=environment_id, update_data=update_data.dict(exclude_unset=True))
    environment = db.query(EnvironmentInstance).filter(
        EnvironmentInstance.id == environment_id
    ).first()

    if not environment:
        log.warning("Update environment failed: not found", environment_id=environment_id)
        raise HTTPException(status_code=404, detail="Environment not found")

    # 업데이트 적용
    update_dict = update_data.dict(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(environment, field, value)

    db.commit()
    db.refresh(environment)
    log.info("Environment updated successfully", environment_id=environment_id)
    return environment


@router.post("/{environment_id}/actions")
async def environment_action(
    environment_id: int,
    action_request: EnvironmentActionRequest,
    db: Session = Depends(get_db)
):
    """환경 액션 실행 (start, stop, restart, delete) - 시연용 (인증 없음)"""
    action = action_request.action
    log.info("Executing environment action", environment_id=environment_id, action=action)
    environment = db.query(EnvironmentInstance).filter(
        EnvironmentInstance.id == environment_id
    ).first()

    if not environment:
        log.warning("Environment action failed: not found", environment_id=environment_id, action=action)
        raise HTTPException(status_code=404, detail="Environment not found")

    env_service = EnvironmentService(db, structlog.get_logger("app.services.environment_service"))

    try:
        if action == "start":
            await env_service.start_environment(environment_id)
        elif action == "stop":
            await env_service.stop_environment(environment_id)
        elif action == "restart":
            await env_service.restart_environment(environment_id)
        elif action == "delete":
            await env_service.delete_environment(environment_id)
        else:
            log.error("Invalid environment action requested", action=action)
            raise HTTPException(status_code=400, detail="Invalid action")
        
        log.info("Environment action executed successfully", environment_id=environment_id, action=action)
        return {"message": f"Action '{action}' executed successfully"}

    except Exception as e:
        log.error("Environment action failed: internal server error", environment_id=environment_id, action=action, error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Action failed: {str(e)}")


@router.get("/{environment_id}/logs")
async def get_environment_logs(
    environment_id: int,
    tail_lines: int = Query(100, ge=1, le=1000, description="Number of log lines to retrieve"),
    db: Session = Depends(get_db)
):
    """환경 로그 조회"""
    log.info("Getting environment logs", environment_id=environment_id, tail_lines=tail_lines)
    environment = db.query(EnvironmentInstance).filter(
        EnvironmentInstance.id == environment_id
    ).first()

    if not environment:
        log.warning("Get logs failed: environment not found", environment_id=environment_id)
        raise HTTPException(status_code=404, detail="Environment not found")

    try:
        k8s_service = KubernetesService()
        logs = await k8s_service.get_pod_logs(
            namespace=environment.k8s_namespace,
            deployment_name=environment.k8s_deployment_name,
            tail_lines=tail_lines
        )
        log.info("Successfully retrieved environment logs", environment_id=environment_id)
        return {"logs": logs}

    except Exception as e:
        log.error("Failed to retrieve environment logs", environment_id=environment_id, error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve logs: {str(e)}")


@router.get("/{environment_id}/access-info")
async def get_access_info(
    environment_id: int,
    db: Session = Depends(get_db)
):
    """환경 접속 정보 조회"""
    log.info("Getting environment access info", environment_id=environment_id)
    environment = db.query(EnvironmentInstance).filter(
        EnvironmentInstance.id == environment_id
    ).first()

    if not environment:
        log.warning("Get access info failed: environment not found", environment_id=environment_id)
        raise HTTPException(status_code=404, detail="Environment not found")

    if environment.status != EnvironmentStatus.RUNNING:
        log.warning("Get access info failed: environment not running", environment_id=environment_id, status=environment.status.value)
        raise HTTPException(status_code=400, detail="Environment is not running")

    return {
        "environment_id": environment.id,
        "access_url": environment.access_url,
        "status": environment.status.value,
        "ports": environment.port_mappings
    }