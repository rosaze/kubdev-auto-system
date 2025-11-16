from typing import List, Optional
from pydantic import BaseModel, Field, HttpUrl


class GitSpec(BaseModel):
    repoUrl: HttpUrl
    ref: Optional[str] = None


class Commands(BaseModel):
    init: Optional[str] = None
    start: Optional[str] = None


class WorkspaceCreateRequest(BaseModel):
    name: str = Field(..., description="Environment name identifier")
    template_id: Optional[str] = Field(None, description="Template identifier")
    git_repository: Optional[HttpUrl] = Field(None, description="Git repository URL")
    ref: Optional[str] = Field(None, description="Git ref")
    image: Optional[str] = Field(None, description="Container image override")
    start_command: Optional[str] = Field(None, description="Start command")
    init_command: Optional[str] = Field(None, description="Init command")
    ports: Optional[List[int]] = Field(default=None, description="Additional ports to expose")
    gitpod_compat: Optional[bool] = Field(default=False, description="If true, parse .gitpod.yml")


class WorkspaceCreateResponse(BaseModel):
    id: str
    status: str
    namespace: Optional[str] = None
    ideUrl: Optional[str] = None

