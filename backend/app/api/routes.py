"""
Main API Router
모든 API 엔드포인트를 모아주는 메인 라우터
"""

from fastapi import APIRouter
from app.api.endpoints import (
    auth,
    environments,
    user,
    monitoring,
    templates,
)

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(user.router, prefix="/users", tags=["Users"])
api_router.include_router(environments.router, prefix="/environments", tags=["Environments"])
api_router.include_router(templates.router, prefix="/templates", tags=["Templates"])
api_router.include_router(monitoring.router, prefix="/monitoring", tags=["Monitoring"])
