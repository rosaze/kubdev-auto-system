import os
import yaml
import httpx
from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import JSONResponse
from backend.auth import get_current_user
from backend.models import WorkspaceCreateRequest, WorkspaceCreateResponse
from backend.k8s_client import create_kubedev_environment


app = FastAPI(title="KubeDev Auto System API", version="0.1.0")


def parse_gitpod_yaml(repo_url: str):
    # Very thin subset: image, tasks.command, ports
    try:
        if repo_url.endswith('.git'):
            raw_base = repo_url[:-4]
        else:
            raw_base = repo_url
        # Try common Git providers raw URL patterns (best-effort)
        if 'github.com' in raw_base:
            # https://github.com/org/repo -> https://raw.githubusercontent.com/org/repo/HEAD/.gitpod.yml
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
    # Namespace where CRs live (controller watches this)
    ctrl_ns = os.getenv("KUBEDEV_CTRL_NS", "kubedev-users")
    env_name = f"env-{user['id']}-{payload.name}"

    spec = {
        "userName": user["name"],
        "templateId": payload.template_id,
        "git": {"repoUrl": str(payload.git_repository), "ref": payload.ref or "main"} if payload.git_repository else None,
        "image": payload.image,
        "commands": {"start": payload.start_command, "init": payload.init_command},
        "ports": payload.ports or [],
    }
    # Clean None values
    spec = {k: v for k, v in spec.items() if v is not None}

    # Thin Gitpod compatibility (optional)
    if payload.gitpod_compat and payload.git_repository:
        compat = parse_gitpod_yaml(str(payload.git_repository))
        # Merge: user input overrides compat
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


@app.get("/healthz")
async def healthz():
    return JSONResponse({"status": "ok"})

