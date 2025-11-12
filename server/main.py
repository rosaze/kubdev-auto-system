"""
KubeDev Auto System - Main FastAPI Application
K8s 기반 자동 개발 환경 프로비저닝 백엔드
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.routes import api_router

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
    try:
        # TODO: 데이터베이스 연결 확인
        # TODO: K8s 클러스터 연결 확인
        return {
            "status": "healthy",
            "database": "connected",
            "kubernetes": "connected"
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Service unhealthy: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )