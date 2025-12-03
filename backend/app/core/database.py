# -*- coding: utf-8 -*-
"""
Database configuration and session management
"""

from sqlalchemy import create_engine, MetaData, text
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from sqlalchemy.pool import StaticPool
from typing import Generator
import logging
import traceback

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Import settings with detailed logging
try:
    logger.info("Importing settings from config...")
    from app.core.config import settings
    logger.info(f"Settings imported successfully. DATABASE_URL: {settings.DATABASE_URL[:30]}...")
except Exception as e:
    logger.error(f"Failed to import settings: {e}")
    logger.error(f"Traceback:\n{traceback.format_exc()}")
    raise

# SQLAlchemy 엔진 생성
try:
    logger.info("Creating SQLAlchemy engine...")
    logger.info(f"Database URL (masked): {settings.DATABASE_URL.split('@')[1] if '@' in settings.DATABASE_URL else 'invalid'}")
    logger.info(f"Pool size: {settings.DATABASE_POOL_SIZE}, Max overflow: {settings.DATABASE_MAX_OVERFLOW}")

    engine = create_engine(
        settings.DATABASE_URL,
        pool_size=settings.DATABASE_POOL_SIZE,
        max_overflow=settings.DATABASE_MAX_OVERFLOW,
        pool_pre_ping=True,
        echo=settings.DEBUG,
        connect_args={"client_encoding": "utf8"},
    )
    logger.info("SQLAlchemy engine created successfully")
except Exception as e:
    logger.error(f"Failed to create SQLAlchemy engine: {e}")
    logger.error(f"Traceback:\n{traceback.format_exc()}")
    raise

# SessionLocal 클래스 생성
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# Base 클래스 생성
Base = declarative_base()

# 메타데이터 설정 (Alembic 마이그레이션용)
metadata = MetaData()


def get_db() -> Generator[Session, None, None]:
    """
    데이터베이스 세션 의존성 주입용 함수
    FastAPI Depends에서 사용
    """
    logger.debug("Creating database session...")
    db = None
    try:
        db = SessionLocal()
        logger.debug("Database session created successfully")
        yield db
    except Exception as e:
        logger.error(f"Database session error: {type(e).__name__}: {str(e)}")
        logger.error(f"Traceback:\n{traceback.format_exc()}")
        if db:
            db.rollback()
        raise
    finally:
        if db:
            db.close()
            logger.debug("Database session closed")


def create_all_tables():
    """
    모든 테이블 생성
    개발 환경에서만 사용 (프로덕션에서는 Alembic 사용)
    """
    try:
        logger.info("Starting table creation...")
        logger.info("Importing models...")

        # 모델 import를 여기서 수행하여 Base.metadata에 등록
        from app.models import User, ProjectTemplate, EnvironmentInstance, ResourceMetric
        logger.info("Models imported successfully")

        logger.info(f"DEBUG mode: {settings.DEBUG}")
        logger.info("Creating database tables...")

        if settings.DEBUG:
            Base.metadata.create_all(bind=engine)
            logger.info("All database tables created (DEBUG mode)")
        else:
            Base.metadata.create_all(bind=engine)
            logger.info("All database tables created (Production mode)")

    except Exception as e:
        logger.error(f"Failed to create tables: {type(e).__name__}: {str(e)}")
        logger.error(f"Traceback:\n{traceback.format_exc()}")
        raise


def check_database_connection() -> bool:
    """
    데이터베이스 연결 상태 확인
    헬스체크에서 사용
    """
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database connection failed: {str(e)}")
        return False


class DatabaseManager:
    """데이터베이스 관리 클래스"""

    def __init__(self):
        self.engine = engine
        self.SessionLocal = SessionLocal

    def get_session(self) -> Session:
        """새 데이터베이스 세션 반환"""
        return self.SessionLocal()

    def close_session(self, session: Session):
        """세션 종료"""
        session.close()

    def execute_query(self, query: str, params: dict = None):
        """쿼리 실행"""
        with self.engine.connect() as connection:
            return connection.execute(text(query), params or {})

    def health_check(self) -> dict:
        """데이터베이스 헬스체크"""
        try:
            with self.engine.connect() as connection:
                result = connection.execute(text("SELECT version()")).fetchone()
                return {
                    "status": "healthy",
                    "version": str(result[0]) if result else "unknown",
                    "pool_size": self.engine.pool.size(),
                    "checked_in": self.engine.pool.checkedin(),
                    "checked_out": self.engine.pool.checkedout()
                }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }


# 전역 데이터베이스 매니저 인스턴스
db_manager = DatabaseManager()


# 트랜잭션 컨텍스트 매니저
class DatabaseTransaction:
    """데이터베이스 트랜잭션 컨텍스트 매니저"""

    def __init__(self):
        self.session = None

    def __enter__(self) -> Session:
        self.session = SessionLocal()
        return self.session

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.session.rollback()
            logger.error(f"Transaction rolled back due to error: {exc_val}")
        else:
            self.session.commit()
        self.session.close()


# 편의 함수들
def with_db_transaction(func):
    """데이터베이스 트랜잭션 데코레이터"""
    def wrapper(*args, **kwargs):
        with DatabaseTransaction() as session:
            kwargs['db'] = session
            return func(*args, **kwargs)
    return wrapper


async def async_get_db() -> Generator[Session, None, None]:
    """비동기 데이터베이스 세션 (FastAPI 비동기 엔드포인트용)"""
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"Async database session error: {str(e)}")
        db.rollback()
        raise
    finally:
        db.close()