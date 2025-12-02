import os
import sys
import uvicorn

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import check_database_connection, create_all_tables
from app.api.routes import api_router
from app.core.logging_config import setup_logging
import logging

logger = logging.getLogger(__name__)

# 로깅 설정
setup_logging()

# 데이터베이스 테이블 생성 (개발 환경)
try:
    create_all_tables()
    logger.info("Database tables initialized successfully")
except Exception as e:
    logger.warning(f"Failed to initialize tables: {e}")

# FastAPI 앱 인스턴스 생성
app = FastAPI(
    title="KubeDev Auto System API",
    description="Kubernetes 기반 자동 개발 환경 프로비저닝 시스템",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_HOSTS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 라우터 등록
app.include_router(api_router, prefix="/api/v1")

@app.get("/")
async def root():
    """헬스체크 엔드포인트"""
    return {
        "message": "KubeDev Auto System API",
        "version": "1.0.0",
        "status": "healthy"
    }

@app.get("/health")
async def health_check():
    """상세 헬스체크"""
    health_status = {
        "status": "healthy",
        "database": "unknown",
        "kubernetes": "unknown",
        "services": {}
    }

    try:
        # 데이터베이스 연결 확인
        if check_database_connection():
            health_status["database"] = "connected"
            health_status["services"]["database"] = "✅ Connected"
        else:
            health_status["database"] = "disconnected"
            health_status["services"]["database"] = "❌ Disconnected"
            health_status["status"] = "degraded"

        # K8s 클러스터 연결 확인
        try:
            from app.services.kubernetes_service import KubernetesService
            k8s_service = KubernetesService()
            cluster_info = await k8s_service.get_cluster_overview()
            if cluster_info:
                health_status["kubernetes"] = "connected"
                health_status["services"]["kubernetes"] = f"✅ Connected ({cluster_info.get('cluster_info', {}).get('total_nodes', 0)} nodes)"
            else:
                health_status["kubernetes"] = "disconnected"
                health_status["services"]["kubernetes"] = "❌ Disconnected"
                health_status["status"] = "degraded"
        except Exception as k8s_error:
            health_status["kubernetes"] = "error"
            health_status["services"]["kubernetes"] = f"⚠️ Error: {str(k8s_error)[:50]}"
            health_status["status"] = "degraded"

        # 전체 상태가 degraded인 경우 503 상태코드 반환
        if health_status["status"] == "degraded":
            raise HTTPException(
                status_code=503,
                detail={
                    "message": "Service partially unavailable",
                    "health_status": health_status
                }
            )

        return health_status

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail={
                "message": f"Service unhealthy: {str(e)}",
                "health_status": health_status
            }
        )

if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host=host, port=port)

