"""
Template API Endpoints
프로젝트 템플릿 관리 API
"""

from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
import uuid
import time
from datetime import datetime

from app.core.database import get_db
from app.models.project_template import ProjectTemplate, TemplateStatus
from app.models.user import User
from app.schemas.project_template import (
    ProjectTemplateCreate,
    ProjectTemplateResponse,
    ProjectTemplateUpdate,
    ProjectTemplateListResponse,
    TemplateValidationResult,
    TemplateDeploymentTest
)
from app.services.kubernetes_service import KubernetesService
from app.services.dockerfile_generator import DockerfileGenerator

router = APIRouter()

@router.post("/upload-yaml")
async def upload_template_yaml(
    current_user_id: int = Form(..., description="업로드하는 사용자 ID"),
    yaml: UploadFile = File(..., description="템플릿 YAML 파일"),
):
    """
    YAML 템플릿 파일 업로드 (프론트엔드 연동용)
    """
    try:
        content = await yaml.read()
        return {
            "status": "uploaded",
            "filename": yaml.filename,
            "size": len(content),
            "uploaded_by": current_user_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process YAML: {str(e)}")


@router.post("/", response_model=ProjectTemplateResponse)
async def create_template(
    template_data: ProjectTemplateCreate,
    created_by: int = Query(..., description="Creator user ID"),
    db: Session = Depends(get_db)
):
    """새 프로젝트 템플릿 생성"""

    # 생성자 확인
    creator = db.query(User).filter(User.id == created_by).first()
    if not creator:
        raise HTTPException(status_code=404, detail="Creator user not found")

    # 같은 이름의 템플릿 중복 체크
    existing = db.query(ProjectTemplate).filter(
        ProjectTemplate.name == template_data.name,
        ProjectTemplate.organization_id == template_data.organization_id
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Template with name '{template_data.name}' already exists in this organization"
        )

    try:
        # 템플릿 생성
        template = ProjectTemplate(
            name=template_data.name,
            description=template_data.description,
            version=template_data.version,
            status=TemplateStatus.DRAFT,
            stack_config=template_data.stack_config,
            dependencies=template_data.dependencies,
            base_image=template_data.base_image,
            custom_dockerfile=template_data.custom_dockerfile,
            init_scripts=template_data.init_scripts,
            post_start_commands=template_data.post_start_commands,
            resource_limits=template_data.resource_limits,
            exposed_ports=template_data.exposed_ports,
            environment_variables=template_data.environment_variables,
            default_git_repo=template_data.default_git_repo,
            git_branch=template_data.git_branch,
            is_public=template_data.is_public,
            organization_id=template_data.organization_id,
            created_by=created_by
        )

        db.add(template)
        db.commit()
        db.refresh(template)

        return template

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create template: {str(e)}")


@router.get("/", response_model=ProjectTemplateListResponse)
async def list_templates(
    organization_id: Optional[int] = Query(None, description="Filter by organization"),
    status: Optional[TemplateStatus] = Query(None, description="Filter by status"),
    is_public: Optional[bool] = Query(None, description="Filter by public/private"),
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(10, ge=1, le=100, description="Page size"),
    db: Session = Depends(get_db)
):
    """템플릿 목록 조회"""

    query = db.query(ProjectTemplate)

    # 필터링
    if organization_id:
        query = query.filter(ProjectTemplate.organization_id == organization_id)
    if status:
        query = query.filter(ProjectTemplate.status == status)
    if is_public is not None:
        query = query.filter(ProjectTemplate.is_public == is_public)

    # 전체 개수
    total = query.count()

    # 페이징
    offset = (page - 1) * size
    templates = query.order_by(ProjectTemplate.created_at.desc()).offset(offset).limit(size).all()

    return ProjectTemplateListResponse(
        templates=templates,
        total=total,
        page=page,
        size=size
    )


@router.get("/{template_id}", response_model=ProjectTemplateResponse)
async def get_template(
    template_id: int,
    db: Session = Depends(get_db)
):
    """특정 템플릿 조회"""

    template = db.query(ProjectTemplate).filter(
        ProjectTemplate.id == template_id
    ).first()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    return template


@router.patch("/{template_id}", response_model=ProjectTemplateResponse)
async def update_template(
    template_id: int,
    update_data: ProjectTemplateUpdate,
    db: Session = Depends(get_db)
):
    """템플릿 업데이트"""

    template = db.query(ProjectTemplate).filter(
        ProjectTemplate.id == template_id
    ).first()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    try:
        # 업데이트 적용
        update_dict = update_data.dict(exclude_unset=True)
        for field, value in update_dict.items():
            setattr(template, field, value)

        # 상태가 ACTIVE로 변경되면 유효성 검증
        if update_data.status == TemplateStatus.ACTIVE:
            validation_result = await validate_template_config(template_id, db)
            if not validation_result.is_valid:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot activate template: {', '.join(validation_result.errors)}"
                )

        db.commit()
        db.refresh(template)

        return template

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update template: {str(e)}")


@router.delete("/{template_id}")
async def delete_template(
    template_id: int,
    force: bool = Query(False, description="Force delete even if in use"),
    db: Session = Depends(get_db)
):
    """템플릿 삭제"""

    template = db.query(ProjectTemplate).filter(
        ProjectTemplate.id == template_id
    ).first()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # 사용 중인 환경이 있는지 확인
    if not force and template.usage_count > 0:
        from app.models.environment import EnvironmentInstance
        active_environments = db.query(EnvironmentInstance).filter(
            EnvironmentInstance.template_id == template_id,
            EnvironmentInstance.status.in_(['running', 'pending', 'creating'])
        ).count()

        if active_environments > 0:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot delete template: {active_environments} environments are still using it"
            )

    try:
        db.delete(template)
        db.commit()

        return {"message": "Template deleted successfully"}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete template: {str(e)}")


@router.post("/{template_id}/validate", response_model=TemplateValidationResult)
async def validate_template_config(
    template_id: int,
    db: Session = Depends(get_db)
):
    """템플릿 설정 유효성 검증"""

    template = db.query(ProjectTemplate).filter(
        ProjectTemplate.id == template_id
    ).first()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    errors = []
    warnings = []

    try:
        # 필수 필드 검증
        if not template.base_image:
            errors.append("Base image is required")

        if not template.stack_config:
            errors.append("Stack configuration is required")

        # 리소스 제한 검증
        if template.resource_limits:
            cpu_limit = template.resource_limits.get("cpu", "")
            memory_limit = template.resource_limits.get("memory", "")

            if not cpu_limit.endswith(('m', '')):
                warnings.append("CPU limit should end with 'm' for millicores")

            if not memory_limit.endswith(('Mi', 'Gi')):
                warnings.append("Memory limit should end with 'Mi' or 'Gi'")

        # Docker 이미지 유효성 검증 (기본적인 형식 체크)
        if '/' not in template.base_image and ':' not in template.base_image:
            warnings.append("Base image should include registry and tag (e.g., 'codercom/code-server:latest')")

        # 포트 설정 검증
        if template.exposed_ports:
            for port in template.exposed_ports:
                if not (1 <= port <= 65535):
                    errors.append(f"Invalid port number: {port}")

        # Git 저장소 URL 검증 (기본적인 형식 체크)
        if template.default_git_repo and not template.default_git_repo.startswith(('http', 'git@')):
            warnings.append("Git repository URL should start with 'http' or 'git@'")

        return TemplateValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Validation failed: {str(e)}")


@router.post("/{template_id}/test-deploy", response_model=TemplateDeploymentTest)
async def test_template_deployment(
    template_id: int,
    timeout_seconds: int = Query(300, description="Test timeout in seconds"),
    db: Session = Depends(get_db)
):
    """템플릿 배포 테스트"""

    template = db.query(ProjectTemplate).filter(
        ProjectTemplate.id == template_id
    ).first()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    try:
        k8s_service = KubernetesService()

        # 테스트용 네임스페이스 생성
        test_namespace = f"test-template-{template_id}-{str(uuid.uuid4())[:8]}"
        test_deployment_name = f"test-{template.name.lower()}-{str(uuid.uuid4())[:8]}"

        start_time = time.time()

        try:
            # 네임스페이스 생성
            await k8s_service.create_namespace(test_namespace)

            # 테스트 배포 생성
            deployment_result = await k8s_service.create_deployment(
                namespace=test_namespace,
                deployment_name=test_deployment_name,
                image=template.base_image,
                environment_vars=template.environment_variables,
                resource_limits=template.resource_limits
            )

            # 배포 상태 확인 (최대 timeout_seconds까지 대기)
            deployment_ready = False
            end_time = start_time + timeout_seconds

            while time.time() < end_time and not deployment_ready:
                status = await k8s_service.get_deployment_status(
                    namespace=test_namespace,
                    deployment_name=test_deployment_name
                )

                if status.get("ready_replicas", 0) >= 1:
                    deployment_ready = True
                    break

                time.sleep(5)  # 5초 대기

            deployment_time = time.time() - start_time

            # 로그 수집
            logs = await k8s_service.get_pod_logs(
                namespace=test_namespace,
                deployment_name=test_deployment_name,
                tail_lines=50
            )

            # 테스트 리소스 정리
            await k8s_service.delete_deployment(test_namespace, test_deployment_name)

            return TemplateDeploymentTest(
                success=deployment_ready,
                deployment_time=deployment_time,
                test_pod_name=f"{test_deployment_name}-xxx",
                error_message=None if deployment_ready else "Deployment did not become ready within timeout",
                logs=logs
            )

        except Exception as test_error:
            # 정리 작업
            try:
                await k8s_service.delete_deployment(test_namespace, test_deployment_name)
            except:
                pass

            return TemplateDeploymentTest(
                success=False,
                deployment_time=time.time() - start_time,
                error_message=str(test_error)
            )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Test deployment failed: {str(e)}")


@router.post("/{template_id}/clone")
async def clone_template(
    template_id: int,
    new_name: str = Query(..., description="Name for the cloned template"),
    created_by: int = Query(..., description="Creator user ID"),
    db: Session = Depends(get_db)
):
    """템플릿 복제"""

    # 원본 템플릿 조회
    source_template = db.query(ProjectTemplate).filter(
        ProjectTemplate.id == template_id
    ).first()

    if not source_template:
        raise HTTPException(status_code=404, detail="Source template not found")

    # 생성자 확인
    creator = db.query(User).filter(User.id == created_by).first()
    if not creator:
        raise HTTPException(status_code=404, detail="Creator user not found")

    # 이름 중복 체크
    existing = db.query(ProjectTemplate).filter(
        ProjectTemplate.name == new_name,
        ProjectTemplate.organization_id == source_template.organization_id
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail=f"Template with name '{new_name}' already exists")

    try:
        # 새 템플릿 생성 (복제)
        cloned_template = ProjectTemplate(
            name=new_name,
            description=f"Cloned from '{source_template.name}' - {source_template.description or ''}",
            version="1.0.0",  # 새 버전으로 시작
            status=TemplateStatus.DRAFT,
            stack_config=source_template.stack_config,
            dependencies=source_template.dependencies,
            base_image=source_template.base_image,
            custom_dockerfile=source_template.custom_dockerfile,
            init_scripts=source_template.init_scripts,
            post_start_commands=source_template.post_start_commands,
            resource_limits=source_template.resource_limits,
            exposed_ports=source_template.exposed_ports,
            environment_variables=source_template.environment_variables,
            default_git_repo=source_template.default_git_repo,
            git_branch=source_template.git_branch,
            is_public=False,  # 복제된 템플릿은 기본적으로 private
            organization_id=source_template.organization_id,
            created_by=created_by
        )

        db.add(cloned_template)
        db.commit()
        db.refresh(cloned_template)

        return {
            "message": "Template cloned successfully",
            "original_template_id": template_id,
            "cloned_template_id": cloned_template.id,
            "cloned_template": cloned_template
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to clone template: {str(e)}")


@router.get("/{template_id}/usage-stats")
async def get_template_usage_stats(
    template_id: int,
    db: Session = Depends(get_db)
):
    """템플릿 사용 통계"""

    template = db.query(ProjectTemplate).filter(
        ProjectTemplate.id == template_id
    ).first()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    try:
        from app.models.environment import EnvironmentInstance

        # 총 사용 횟수
        total_usage = db.query(EnvironmentInstance).filter(
            EnvironmentInstance.template_id == template_id
        ).count()

        # 현재 활성 환경
        active_environments = db.query(EnvironmentInstance).filter(
            EnvironmentInstance.template_id == template_id,
            EnvironmentInstance.status.in_(['running', 'pending', 'creating'])
        ).count()

        # 최근 7일 사용량
        from datetime import timedelta
        recent_usage = db.query(EnvironmentInstance).filter(
            EnvironmentInstance.template_id == template_id,
            EnvironmentInstance.created_at >= datetime.utcnow() - timedelta(days=7)
        ).count()

        # 사용자별 통계
        user_usage = db.query(
            User.email,
            db.func.count(EnvironmentInstance.id).label('usage_count')
        ).join(
            EnvironmentInstance, User.id == EnvironmentInstance.user_id
        ).filter(
            EnvironmentInstance.template_id == template_id
        ).group_by(User.email).all()

        return {
            "template_id": template_id,
            "template_name": template.name,
            "total_usage": total_usage,
            "active_environments": active_environments,
            "recent_usage_7days": recent_usage,
            "user_usage": [{"email": email, "count": count} for email, count in user_usage],
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get usage stats: {str(e)}")


# =====================================
# 🚀 YAML 업로드 → 템플릿 생성 (통합 API)
# =====================================

@router.post("/create-from-yaml", response_model=ProjectTemplateResponse)
async def create_template_from_yaml(
    template_name: str = Form(..., description="Template name"),
    yaml_file: UploadFile = File(..., description="YAML file to upload"),
    git_repository: Optional[str] = Form(None, description="Git repository URL (optional)"),
    description: Optional[str] = Form("YAML로 생성된 템플릿", description="Template description"),
    created_by: int = Form(..., description="Creator user ID"),
    db: Session = Depends(get_db)
):
    """YAML 파일로부터 직접 템플릿 생성 - 업로드부터 저장까지 한 번에!"""

    try:
        import yaml

        # 1. 생성자 확인
        creator = db.query(User).filter(User.id == created_by).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator user not found")

        # 2. 파일 확장자 확인
        if not yaml_file.filename.lower().endswith(('.yaml', '.yml')):
            raise HTTPException(status_code=400, detail="Invalid file type. Only .yaml or .yml files are accepted.")

        # 3. YAML 파일 읽기 및 파싱 (다중 인코딩 지원)
        try:
            yaml_content = await yaml_file.read()

            # 여러 인코딩 시도
            encodings = ['utf-8', 'utf-8-sig', 'cp949', 'euc-kr', 'latin-1']
            yaml_text = None
            used_encoding = None

            for encoding in encodings:
                try:
                    yaml_text = yaml_content.decode(encoding)
                    used_encoding = encoding
                    break
                except UnicodeDecodeError:
                    continue

            if yaml_text is None:
                raise HTTPException(
                    status_code=400,
                    detail="Could not decode file. Please save as UTF-8 encoding."
                )

            parsed_yaml = yaml.safe_load(yaml_text)
            if not parsed_yaml:
                raise HTTPException(status_code=400, detail="Invalid YAML format or empty file")

        except yaml.YAMLError as e:
            raise HTTPException(status_code=400, detail=f"YAML parsing error: {str(e)}")

        # 3. Git 정보 추출
        git_info = {}
        if git_repository:
            git_info = {"repository_url": git_repository, "branch": "main"}
        elif "github" in parsed_yaml:
            github_config = parsed_yaml["github"]
            if isinstance(github_config, str):
                git_info["repository_url"] = f"https://github.com/{github_config}"
        elif "git" in parsed_yaml:
            git_config = parsed_yaml["git"]
            if isinstance(git_config, dict):
                git_info["repository_url"] = git_config.get("repository", git_config.get("repo"))
                git_info["branch"] = git_config.get("branch", git_config.get("ref", "main"))

        # 4. Gitpod 설정 자동 파싱 (GitHub에서 .gitpod.yml 가져오기)
        if git_info.get("repository_url"):
            gitpod_config = await parse_gitpod_yaml_from_repo(git_info["repository_url"])
            if gitpod_config:
                for key, value in gitpod_config.items():
                    if key not in parsed_yaml:
                        parsed_yaml[key] = value

        # 5. 환경 설정 생성
        environment_config = extract_environment_config(parsed_yaml, git_info)

        # 6. 템플릿 중복 확인
        existing = db.query(ProjectTemplate).filter(
            ProjectTemplate.name == template_name
        ).first()

        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Template '{template_name}' already exists"
            )

        # 7. 템플릿 생성 및 저장
        template = ProjectTemplate(
            name=template_name,
            description=description,
            version="1.0.0",
            status=TemplateStatus.ACTIVE,  # 바로 활성화
            stack_config=parsed_yaml,
            base_image=environment_config.get("base_image", "codercom/code-server:latest"),
            init_scripts=environment_config.get("init_scripts", []),
            post_start_commands=environment_config.get("post_start_commands", []),
            resource_limits={
                "cpu": "1000m",
                "memory": "2Gi",
                "storage": "10Gi"
            },
            exposed_ports=environment_config.get("exposed_ports", [8080]),
            environment_variables=environment_config.get("environment_variables", {}),
            default_git_repo=environment_config.get("git_repository"),
            git_branch=environment_config.get("git_branch", "main"),
            is_public=False,
            created_by=created_by
        )

        db.add(template)
        db.commit()
        db.refresh(template)

        # ========================================
        # 🚀 검증용 KubeDevEnvironment CRD 생성
        # ========================================
        try:
            from app.services.kubernetes_service import KubernetesService
            from app.models.environment import EnvironmentInstance, EnvironmentStatus
            import logging

            logger = logging.getLogger(__name__)
            logger.info(f"Creating validation environment for template: {template.name}")

            k8s_service = KubernetesService()

            # CRD 이름 및 네임스페이스
            crd_name = f"validation-{template.name.lower().replace(' ', '-')}"
            crd_namespace = "kubdev-users"

            # KubeDevEnvironment CRD 객체 생성
            crd_object = {
                "apiVersion": "kubedev.my-project.com/v1alpha1",
                "kind": "KubeDevEnvironment",
                "metadata": {
                    "name": crd_name,
                    "namespace": crd_namespace
                },
                "spec": {
                    "userName": f"validation-{template.name}",
                    "gitRepository": template.default_git_repo or "",
                    "image": template.base_image,
                    "commands": {
                        "init": "\n".join(template.init_scripts) if template.init_scripts else "",
                        "start": "\n".join(template.post_start_commands) if template.post_start_commands else ""
                    },
                    "ports": template.exposed_ports or [8080],
                    "storage": {
                        "size": template.resource_limits.get("storage", "10Gi") if template.resource_limits else "10Gi"
                    }
                }
            }

            # CRD 생성
            logger.info(f"Applying KubeDevEnvironment CRD: {crd_name}")
            await k8s_service.create_custom_object(crd_object)
            logger.info(f"✅ Validation environment CRD created: {crd_name}")

            # 검증용 환경 DB 레코드 생성 (선택사항 - 추적용)
            validation_env = EnvironmentInstance(
                name=f"Validation: {template.name}",
                template_id=template.id,
                user_id=created_by,  # 템플릿 생성자가 소유
                k8s_namespace=crd_namespace,
                k8s_deployment_name=crd_name,
                status=EnvironmentStatus.CREATING,
                git_repository=template.default_git_repo,
                git_branch=template.git_branch
            )
            db.add(validation_env)
            db.commit()
            db.refresh(validation_env)

            logger.info(f"✅ Validation environment DB record created: {validation_env.id}")

        except Exception as crd_error:
            logger.error(f"Failed to create validation CRD: {str(crd_error)}")
            # CRD 생성 실패해도 템플릿은 저장됨 (경고만 표시)
            # 필요하면 여기서 예외를 던져서 전체 트랜잭션 롤백 가능

        return template

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Template creation failed: {str(e)}")


# =====================================
# 🚀 Git 리포지토리 파싱 API
# =====================================

@router.post("/parse-yaml")
async def parse_yaml_with_git_info(
    yaml_content: str = Query(..., description="YAML content to parse"),
    git_repository: Optional[str] = Query(None, description="Git repository URL")
):
    """YAML 내용 파싱 및 Git 리포지토리 정보 추출"""

    try:
        import yaml

        # YAML 파싱
        parsed_yaml = yaml.safe_load(yaml_content)
        if not parsed_yaml:
            raise HTTPException(status_code=400, detail="Invalid YAML format")

        # Git 리포지토리 정보 추출
        git_info = {}

        # 1. 직접 전달된 git_repository 사용
        if git_repository:
            git_info = {
                "repository_url": git_repository,
                "branch": "main"
            }

        # 2. YAML 내에서 Git 정보 추출 (Gitpod 형식 지원)
        elif "github" in parsed_yaml:
            github_config = parsed_yaml["github"]
            if isinstance(github_config, str):
                git_info["repository_url"] = f"https://github.com/{github_config}"
            elif isinstance(github_config, dict) and "repository" in github_config:
                git_info["repository_url"] = github_config["repository"]

        elif "git" in parsed_yaml:
            git_config = parsed_yaml["git"]
            if isinstance(git_config, dict):
                git_info["repository_url"] = git_config.get("repository", git_config.get("repo"))
                git_info["branch"] = git_config.get("branch", git_config.get("ref", "main"))

        # 3. 리포지토리 URL이 .gitpod.yml 등을 가리키는 경우 파싱
        if git_info.get("repository_url"):
            gitpod_config = await parse_gitpod_yaml_from_repo(git_info["repository_url"])
            if gitpod_config:
                # Gitpod 설정과 병합
                for key, value in gitpod_config.items():
                    if key not in parsed_yaml:
                        parsed_yaml[key] = value

        # 환경 설정 정보 추출
        environment_config = extract_environment_config(parsed_yaml, git_info)

        return {
            "git_info": git_info,
            "environment_config": environment_config,
            "parsed_yaml": parsed_yaml,
            "timestamp": datetime.utcnow().isoformat()
        }

    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"YAML parsing error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Parsing failed: {str(e)}")


async def parse_gitpod_yaml_from_repo(repo_url: str) -> dict[str, Any]:
    """Git 리포지토리에서 .gitpod.yml 파싱"""
    try:
        import httpx
        import yaml

        # URL 정규화
        if repo_url.endswith('.git'):
            raw_base = repo_url[:-4]
        else:
            raw_base = repo_url

        # GitHub Raw URL 생성
        if 'github.com' in raw_base:
            parts = raw_base.split('github.com/')[-1]
            raw_url = f"https://raw.githubusercontent.com/{parts}/HEAD/.gitpod.yml"
        elif 'gitlab.com' in raw_base:
            parts = raw_base.split('gitlab.com/')[-1]
            raw_url = f"https://gitlab.com/{parts}/-/raw/HEAD/.gitpod.yml"
        else:
            return {}

        # .gitpod.yml 다운로드 및 파싱
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(raw_url)

        if response.status_code != 200:
            return {}

        gitpod_data = yaml.safe_load(response.text) or {}
        return extract_gitpod_config(gitpod_data)

    except Exception:
        return {}


def extract_gitpod_config(gitpod_data: dict[str, Any]) -> dict[str, Any]:
    """Gitpod YAML에서 환경 설정 추출"""
    config = {}

    # Docker 이미지
    if isinstance(gitpod_data.get('image'), str):
        config['image'] = gitpod_data['image']

    # 작업 명령어
    tasks = gitpod_data.get('tasks')
    if isinstance(tasks, list) and tasks:
        commands = {}
        for i, task in enumerate(tasks):
            if isinstance(task, dict):
                if task.get('init'):
                    commands[f'init_{i}' if i > 0 else 'init'] = task['init']
                if task.get('command'):
                    commands[f'command_{i}' if i > 0 else 'start'] = task['command']
                if task.get('before'):
                    commands[f'before_{i}' if i > 0 else 'before'] = task['before']
        if commands:
            config['commands'] = commands

    # 포트 설정
    ports = gitpod_data.get('ports')
    if isinstance(ports, list):
        parsed_ports = []
        for port in ports:
            if isinstance(port, int):
                parsed_ports.append(port)
            elif isinstance(port, dict) and isinstance(port.get('port'), int):
                parsed_ports.append(port['port'])
        if parsed_ports:
            config['ports'] = parsed_ports

    # VSCode 확장
    vscode_config = gitpod_data.get('vscode')
    if isinstance(vscode_config, dict):
        extensions = vscode_config.get('extensions')
        if isinstance(extensions, list):
            config['vscode_extensions'] = extensions

    return config


def extract_environment_config(parsed_yaml: dict[str, Any], git_info: dict[str, Any]) -> dict[str, Any]:
    """YAML과 Git 정보로부터 환경 설정 추출"""
    config = {
        "base_image": parsed_yaml.get("image", "codercom/code-server:latest"),
        "exposed_ports": parsed_yaml.get("ports", [8080]),
        "environment_variables": parsed_yaml.get("env", {}),
        "git_repository": git_info.get("repository_url"),
        "git_branch": git_info.get("branch", "main")
    }

    # 명령어 처리
    commands = parsed_yaml.get("commands", {})
    if commands:
        config["init_scripts"] = []
        config["post_start_commands"] = []

        if commands.get("init"):
            config["init_scripts"].append(commands["init"])
        if commands.get("before"):
            config["init_scripts"].insert(0, commands["before"])
        if commands.get("start") or commands.get("command"):
            config["post_start_commands"].append(commands.get("start") or commands.get("command"))

    # VSCode 확장을 환경변수로 설정
    if parsed_yaml.get("vscode_extensions"):
        config["environment_variables"]["VSCODE_EXTENSIONS"] = ",".join(parsed_yaml["vscode_extensions"])

    # Git 클론 명령어 자동 추가
    if config.get("git_repository"):
        git_clone_script = f"""
# Git 리포지토리 자동 클론
if [ ! -d "/workspace/.git" ]; then
    echo "📥 Git 리포지토리 클론 중..."
    git clone {config["git_repository"]} /workspace/project
    cd /workspace/project
    git checkout {config["git_branch"]}
    echo "✅ Git 리포지토리 클론 완료"
fi
"""
        config.setdefault("init_scripts", []).insert(0, git_clone_script)

        # Git 설정 추가
        config["environment_variables"].update({
            "GIT_REPO": config["git_repository"],
            "GIT_BRANCH": config["git_branch"],
            "WORKSPACE": "/workspace/project"
        })

    return config


# =====================================
# 🚀 Dockerfile 자동 생성 API
# =====================================

@router.post("/generate-dockerfile")
async def generate_dockerfile_from_stack(
    stack_config: dict,
    environment_id: str = Query(..., description="Environment ID for image naming"),
    validate_only: bool = Query(False, description="Only validate without building")
):
    """스택 설정으로 Dockerfile 자동 생성"""

    dockerfile_generator = DockerfileGenerator()

    try:
        # 1. 스택 설정 유효성 검증
        is_valid, errors = dockerfile_generator.validate_stack_config(stack_config)
        if not is_valid:
            raise HTTPException(
                status_code=400,
                detail={"message": "Invalid stack configuration", "errors": errors}
            )

        # 2. Dockerfile 생성
        dockerfile_content = dockerfile_generator.generate_dockerfile(stack_config, environment_id)

        if validate_only:
            return {
                "status": "validated",
                "dockerfile": dockerfile_content,
                "stack_config": stack_config,
                "environment_id": environment_id
            }

        # 3. Docker 이미지 빌드 및 푸시
        image_tag, build_success = await dockerfile_generator.build_and_push_image(
            environment_id=environment_id,
            dockerfile_content=dockerfile_content,
            stack_config=stack_config
        )

        if not build_success:
            raise HTTPException(
                status_code=500,
                detail="Failed to build Docker image"
            )

        return {
            "status": "success",
            "dockerfile": dockerfile_content,
            "image_tag": image_tag,
            "environment_id": environment_id,
            "stack_config": stack_config,
            "build_time": datetime.utcnow().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Dockerfile generation failed: {str(e)}")


@router.get("/supported-stacks")
async def get_supported_stacks():
    """지원되는 스택 목록 조회"""

    dockerfile_generator = DockerfileGenerator()

    try:
        supported_stacks = dockerfile_generator.get_supported_stacks()

        return {
            "supported_stacks": supported_stacks,
            "examples": {
                "node_react": {
                    "language": "node",
                    "version": "18",
                    "framework": "react",
                    "dependencies": ["axios", "react-router-dom"],
                    "exposed_ports": [3000],
                    "environment_variables": {
                        "NODE_ENV": "development"
                    }
                },
                "python_fastapi": {
                    "language": "python",
                    "version": "3.11",
                    "framework": "fastapi",
                    "dependencies": ["sqlalchemy", "pandas"],
                    "exposed_ports": [8000],
                    "environment_variables": {
                        "PYTHONPATH": "/workspace"
                    }
                },
                "java_spring": {
                    "language": "java",
                    "version": "17",
                    "framework": "spring",
                    "dependencies": [],
                    "exposed_ports": [8080],
                    "environment_variables": {
                        "SPRING_PROFILES_ACTIVE": "development"
                    }
                }
            },
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get supported stacks: {str(e)}")


@router.post("/{template_id}/generate-custom-image")
async def generate_custom_image_for_template(
    template_id: int,
    build_now: bool = Query(True, description="Build image immediately"),
    db: Session = Depends(get_db)
):
    """기존 템플릿에서 커스텀 이미지 생성"""

    # 템플릿 조회
    template = db.query(ProjectTemplate).filter(
        ProjectTemplate.id == template_id
    ).first()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    if not template.stack_config:
        raise HTTPException(
            status_code=400,
            detail="Template must have stack_config to generate custom image"
        )

    dockerfile_generator = DockerfileGenerator()

    try:
        # 1. 스택 설정 유효성 검증
        is_valid, errors = dockerfile_generator.validate_stack_config(template.stack_config)
        if not is_valid:
            raise HTTPException(
                status_code=400,
                detail={"message": "Invalid template stack configuration", "errors": errors}
            )

        # 2. Environment ID 생성 (템플릿 기반)
        environment_id = f"template-{template_id}-{str(uuid.uuid4())[:8]}"

        # 3. Dockerfile 생성
        dockerfile_content = dockerfile_generator.generate_dockerfile(
            template.stack_config,
            environment_id
        )

        if not build_now:
            return {
                "status": "generated",
                "template_id": template_id,
                "template_name": template.name,
                "dockerfile": dockerfile_content,
                "environment_id": environment_id,
                "message": "Dockerfile generated. Use build_now=true to build image."
            }

        # 4. 이미지 빌드 및 푸시
        image_tag, build_success = await dockerfile_generator.build_and_push_image(
            environment_id=environment_id,
            dockerfile_content=dockerfile_content,
            stack_config=template.stack_config
        )

        if not build_success:
            raise HTTPException(status_code=500, detail="Failed to build custom image")

        # 5. 템플릿의 base_image 업데이트 (선택사항)
        # template.base_image = image_tag
        # db.commit()

        return {
            "status": "success",
            "template_id": template_id,
            "template_name": template.name,
            "dockerfile": dockerfile_content,
            "image_tag": image_tag,
            "environment_id": environment_id,
            "build_time": datetime.utcnow().isoformat(),
            "message": f"Custom image built successfully: {image_tag}"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Custom image generation failed: {str(e)}"
        )
