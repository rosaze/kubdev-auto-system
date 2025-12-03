# -*- coding: utf-8 -*-
"""
Configuration settings for KubeDev Auto System
"""

from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import validator
import os
import sys
import logging

# Configure logging for config module
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Log encoding information
logger.info(f"Python version: {sys.version}")
logger.info(f"Default encoding: {sys.getdefaultencoding()}")
logger.info(f"File system encoding: {sys.getfilesystemencoding()}")
try:
    import locale
    logger.info(f"Locale preferred encoding: {locale.getpreferredencoding()}")
except Exception as e:
    logger.warning(f"Could not get locale encoding: {e}")


class Settings(BaseSettings):
    """애플리케이션 설정"""

    # 애플리케이션 기본 설정
    APP_NAME: str = "KubeDev Auto System"
    DEBUG: bool = False
    VERSION: str = "1.0.0"
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # CORS 설정
    ALLOWED_HOSTS: List[str] = ["http://localhost:3000", "http://localhost:8000"]

    # 데이터베이스 설정
    DATABASE_URL: str = "postgresql://kubdev:password@localhost:5432/kubdev"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 0

    # Redis 설정
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT 및 보안 설정
    SECRET_KEY: str = "your-super-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Kubernetes 설정
    KUBECONFIG_PATH: Optional[str] = None
    K8S_NAMESPACE: str = "kubdev"

    # 기본 리소스 제한
    DEFAULT_CPU_LIMIT: str = "1000m"  # 1 CPU core
    DEFAULT_MEMORY_LIMIT: str = "2Gi"  # 2GB
    DEFAULT_STORAGE_LIMIT: str = "10Gi"  # 10GB
    DEFAULT_POD_LIMIT: int = 5

    # 환경 관리 설정
    ENVIRONMENT_TIMEOUT_HOURS: int = 8
    AUTO_CLEANUP_ENABLED: bool = True
    CLEANUP_CHECK_INTERVAL_MINUTES: int = 30

    # Docker 설정
    DOCKER_REGISTRY: str = "docker.io"
    DOCKER_USERNAME: Optional[str] = None
    DOCKER_PASSWORD: Optional[str] = None
    DOCKER_NAMESPACE: str = "kubdev"

    # IDE 이미지 설정
    BASE_IDE_IMAGES: dict = {
        "code-server": "codercom/code-server:latest",
        "jupyter": "jupyter/datascience-notebook:latest",
        "theia": "theiaide/theia-python:latest"
    }

    # 모니터링 설정
    PROMETHEUS_ENABLED: bool = True
    PROMETHEUS_PORT: int = 8001
    METRICS_COLLECTION_INTERVAL: int = 60  # seconds

    # 로깅 설정
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"

    @validator("ALLOWED_HOSTS", pre=True)
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [host.strip() for host in v.split(",")]
        return v

    @validator("KUBECONFIG_PATH")
    def validate_kubeconfig(cls, v):
        if v is None:
            # 기본 kubeconfig 경로 사용
            home = os.path.expanduser("~")
            default_path = os.path.join(home, ".kube", "config")
            if os.path.exists(default_path):
                return default_path
            return None
        return v

    class Config:
        # Disable .env file to avoid encoding issues on Windows
        # env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# 전역 설정 인스턴스
try:
    logger.info("Creating Settings instance...")
    logger.info(f"Current working directory: {os.getcwd()}")
    logger.info(f"Environment variables: DATABASE_URL={os.getenv('DATABASE_URL', 'NOT SET')}")
    settings = Settings()
    logger.info("Settings instance created successfully")
    logger.info(f"DATABASE_URL from settings: {settings.DATABASE_URL}")
except Exception as e:
    logger.error(f"Failed to create Settings instance: {e}")
    logger.error(f"Error type: {type(e).__name__}")
    logger.error(f"Error details: {str(e)}")
    import traceback
    logger.error(f"Traceback:\n{traceback.format_exc()}")
    raise


def get_database_url() -> str:
    """데이터베이스 URL 반환"""
    return settings.DATABASE_URL


def get_redis_url() -> str:
    """Redis URL 반환"""
    return settings.REDIS_URL


def is_production() -> bool:
    """프로덕션 환경 여부 확인"""
    return not settings.DEBUG


def get_kubernetes_config_path() -> Optional[str]:
    """Kubernetes 설정 파일 경로 반환"""
    return settings.KUBECONFIG_PATH