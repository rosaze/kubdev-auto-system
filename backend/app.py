import os
import yaml
import httpx
from fastapi import FastAPI, Depends, HTTPException, Path, Query, File, UploadFile
from fastapi.responses import JSONResponse
from backend.auth import get_current_user
from backend.models import (
    WorkspaceCreateRequest,
    WorkspaceCreateResponse,
    WorkspaceItem,
    AdminBatchCreateRequest,
    AdminBatchCreateResponse,
)
from backend.k8s_client import (
    create_kubedev_environment,
    get_kubedev_environment,
    list_kubedev_environments,
    delete_kubedev_environment,
    scale_deployment,
    delete_namespace,
)


app = FastAPI(title="KubeDev Auto System API", version="0.2.0")


def parse_gitpod_yaml(repo_url: str):
    # Very thin subset: image, tasks.command, ports
    try:
        if repo_url.endswith('.git'):
            raw_base = repo_url[:-4]
        else:
            raw_base = repo_url
        if 'github.com' in raw_base:
            parts = raw_base.split('github.com/')[-1]
            raw_url = f"https://raw.githubusercontent.com/{parts}/HEAD/.gitpod.yml"
        elif 'gitlab.com' in raw_base:
            parts = raw_base.split('gitlab.com/')[-1]
            raw_url = f"https://gitlab.com/{parts}/-/raw/HEAD/.gitpod.yml"
        else:
            return {}
        r = httpx.get(raw_url, timeout=5.0)
        if r.status_code != 200:
            return {}
        data = yaml.safe_load(r.text) or {}
        out = {}
        if isinstance(data.get('image'), str):
            out['image'] = data['image']
        tasks = data.get('tasks')
        if isinstance(tasks, list) and tasks:
            t0 = tasks[0] or {}
            cmd = t0.get('command')
            if isinstance(cmd, str):
                out.setdefault('commands', {})['start'] = cmd
            init = t0.get('init')
            if isinstance(init, str):
                out.setdefault('commands', {})['init'] = init
        ports = data.get('ports')
        if isinstance(ports, list):
            out['ports'] = []
            for p in ports:
                if isinstance(p, int):
                    out['ports'].append(p)
                elif isinstance(p, dict) and isinstance(p.get('port'), int):
                    out['ports'].append(p['port'])
        return out
    except Exception:
        return {}


@app.post("/me/workspaces", response_model=WorkspaceCreateResponse)
async def create_workspace(payload: WorkspaceCreateRequest, user=Depends(get_current_user)):
    ctrl_ns = os.getenv("KUBEDEV_CTRL_NS", "kubedev-users")
    env_name = f"env-{user['id']}-{payload.name}"

    spec = {
        "userName": user["name"],
        "templateId": payload.template_id,
        "git": {"repoUrl": str(payload.git_repository), "ref": payload.ref or "main"} if payload.git_repository else None,
        "image": payload.image,
        "commands": {"start": payload.start_command, "init": payload.init_command},
        "ports": payload.ports or [],
        "mode": payload.mode,
    }
    spec = {k: v for k, v in spec.items() if v is not None}

    if payload.gitpod_compat and payload.git_repository:
        compat = parse_gitpod_yaml(str(payload.git_repository))
        for k, v in compat.items():
            if k == 'commands':
                spec.setdefault('commands', {})
                for ck, cv in v.items():
                    spec['commands'].setdefault(ck, cv)
            elif k == 'ports':
                existing = set(spec.get('ports', []))
                spec['ports'] = list(existing.union(set(v)))
            else:
                spec.setdefault(k, v)

    created = create_kubedev_environment(env_name, ctrl_ns, spec)
    status = created.get('status') or {}
    return WorkspaceCreateResponse(id=env_name, status=status.get('phase', 'Pending'), namespace=status.get('namespace'), ideUrl=status.get('ideUrl'))


@app.get("/me/workspaces", response_model=list[WorkspaceItem])
async def list_my_workspaces(user=Depends(get_current_user)):
    ctrl_ns = os.getenv("KUBEDEV_CTRL_NS", "kubedev-users")
    items = list_kubedev_environments(ctrl_ns)
    out: list[WorkspaceItem] = []
    for it in items:
        spec = it.get('spec', {})
        if spec.get('userName') != user['name']:
            continue
        st = it.get('status', {})
        out.append(
            WorkspaceItem(
                id=it['metadata']['name'],
                userName=spec.get('userName', ''),
                status=st.get('phase'),
                namespace=st.get('namespace'),
                ideUrl=st.get('ideUrl'),
                createdAt=it['metadata'].get('creationTimestamp'),
                templateId=spec.get('templateId'),
            )
        )
    return out


@app.post("/me/workspaces/{wid}/stop")
async def stop_workspace(wid: str = Path(...), user=Depends(get_current_user)):
    ctrl_ns = os.getenv("KUBEDEV_CTRL_NS", "kubedev-users")
    cr = get_kubedev_environment(wid, ctrl_ns)
    spec = cr.get('spec', {})
    if spec.get('userName') != user['name']:
        raise HTTPException(status_code=403, detail="Forbidden")
    ns = (cr.get('status') or {}).get('namespace')
    if not ns:
        raise HTTPException(status_code=409, detail="Workspace not ready")
    scale_deployment(ns, f"ide-{wid}", 0)
    return {"status": "Hibernating"}


@app.post("/me/workspaces/{wid}/start")
async def start_workspace(wid: str = Path(...), user=Depends(get_current_user)):
    ctrl_ns = os.getenv("KUBEDEV_CTRL_NS", "kubedev-users")
    cr = get_kubedev_environment(wid, ctrl_ns)
    spec = cr.get('spec', {})
    if spec.get('userName') != user['name']:
        raise HTTPException(status_code=403, detail="Forbidden")
    ns = (cr.get('status') or {}).get('namespace')
    if not ns:
        raise HTTPException(status_code=409, detail="Workspace not ready")
    scale_deployment(ns, f"ide-{wid}", 1)
    return {"status": "Running"}


@app.delete("/me/workspaces/{wid}")
async def delete_workspace(wid: str = Path(...),
                           delete_namespace_first: bool = Query(True),
                           user=Depends(get_current_user)):
    ctrl_ns = os.getenv("KUBEDEV_CTRL_NS", "kubedev-users")
    cr = get_kubedev_environment(wid, ctrl_ns)
    spec = cr.get('spec', {})
    if spec.get('userName') != user['name']:
        raise HTTPException(status_code=403, detail="Forbidden")
    ns = (cr.get('status') or {}).get('namespace')
    if delete_namespace_first and ns:
        delete_namespace(ns)
    delete_kubedev_environment(wid, ctrl_ns)
    return {"deleted": wid}


def _ensure_admin(user: dict):
    if user.get('role') != 'admin':
        raise HTTPException(status_code=403, detail="Admin only")


@app.post("/admin/workspaces/batch", response_model=AdminBatchCreateResponse)
async def admin_batch_create(payload: AdminBatchCreateRequest, user=Depends(get_current_user)):
    _ensure_admin(user)
    ctrl_ns = os.getenv("KUBEDEV_CTRL_NS", "kubedev-users")
    created_list: list[WorkspaceCreateResponse] = []
    failed: list[str] = []
    for uname in payload.users:
        env_name = f"env-{uname}-{payload.name}"
        spec = {
            "userName": uname,
            "templateId": payload.template_id,
            "git": {"repoUrl": str(payload.git_repository), "ref": payload.ref or "main"} if payload.git_repository else None,
            "image": payload.image,
            "commands": {"start": payload.start_command, "init": payload.init_command},
            "ports": payload.ports or [],
            "mode": payload.mode,
        }
        spec = {k: v for k, v in spec.items() if v is not None}
        try:
            created = create_kubedev_environment(env_name, ctrl_ns, spec)
            st = created.get('status') or {}
            created_list.append(WorkspaceCreateResponse(id=env_name, status=st.get('phase', 'Pending'), namespace=st.get('namespace'), ideUrl=st.get('ideUrl')))
        except Exception as e:
            failed.append(f"{uname}: {e}")
    return AdminBatchCreateResponse(created=created_list, failed=failed)


@app.post("/admin/upload-environment")
async def upload_environment_yaml(
    file: UploadFile = File(...),
    user_name: str = Query(..., description="Username for the environment"),
    user=Depends(get_current_user)
):
    """Upload YAML file and create KubeDevEnvironment"""
    _ensure_admin(user)

    # Validate file type
    if not file.filename or not file.filename.endswith(('.yaml', '.yml')):
        raise HTTPException(status_code=400, detail="Only YAML files are allowed")

    try:
        # Read and parse YAML content
        content = await file.read()
        yaml_data = yaml.safe_load(content.decode('utf-8'))

        # Extract environment configuration from YAML
        # Support both Gitpod-style and KubeDevEnvironment-style YAML
        spec = {}
        spec["userName"] = user_name

        # Handle Gitpod-style YAML
        if "image" in yaml_data:
            spec["image"] = yaml_data["image"]

        if "tasks" in yaml_data and isinstance(yaml_data["tasks"], list):
            commands = {}
            for task in yaml_data["tasks"]:
                if "init" in task:
                    commands["init"] = task["init"]
                if "command" in task:
                    commands["start"] = task["command"]
            if commands:
                spec["commands"] = commands

        if "ports" in yaml_data:
            spec["ports"] = yaml_data["ports"]

        if "github" in yaml_data or "vscode" in yaml_data:
            # Extract git repository info
            git_info = {}
            if "github" in yaml_data:
                repo = yaml_data["github"]
                if isinstance(repo, dict) and "prebuilds" in repo:
                    git_info["repoUrl"] = f"https://github.com/{repo.get('prebuilds', {}).get('master', {}).get('repository', '')}"
                elif isinstance(repo, str):
                    git_info["repoUrl"] = f"https://github.com/{repo}"
            if git_info:
                spec["git"] = git_info

        # Handle direct KubeDevEnvironment-style YAML
        if "spec" in yaml_data:
            kube_spec = yaml_data["spec"]
            spec.update({k: v for k, v in kube_spec.items() if v is not None})

        # Generate environment name
        import uuid
        env_name = f"env-{user_name}-{str(uuid.uuid4())[:8]}"

        # Create KubeDevEnvironment CR
        ctrl_ns = os.getenv("KUBEDEV_CTRL_NS", "kubedev-users")
        created = create_kubedev_environment(env_name, ctrl_ns, spec)
        status = created.get('status') or {}

        return {
            "success": True,
            "environment_id": env_name,
            "status": status.get('phase', 'Pending'),
            "namespace": status.get('namespace'),
            "ideUrl": status.get('ideUrl'),
            "parsed_spec": spec,
            "message": f"Environment created successfully from {file.filename}"
        }

    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML format: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create environment: {str(e)}")


@app.get("/healthz")
async def healthz():
    return JSONResponse({"status": "ok"})
