"""
Database configuration and session management
SQLAlchemy 데이터베이스 설정 및 세션 관리
"""

from sqlalchemy import create_engine, MetaData
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from sqlalchemy.pool import StaticPool
from app.core.config import settings
from typing import Generator
import logging

logger = logging.getLogger(__name__)

# SQLAlchemy 엔진 생성
engine = create_engine(
    settings.DATABASE_URL,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_pre_ping=True,  # 연결 검증
    echo=settings.DEBUG,  # SQL 쿼리 로깅 (개발 환경에서만)
    connect_args={"client_encoding": "utf8"},  # 인코딩 강제
)

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
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"Database session error: {str(e)}")
        db.rollback()
        raise
    finally:
        db.close()


def create_all_tables():
    """
    모든 테이블 생성
    개발 환경에서만 사용 (프로덕션에서는 Alembic 사용)
    """
    # 모델 import를 여기서 수행하여 Base.metadata에 등록
    from app.models import User, Organization, Team, ProjectTemplate, EnvironmentInstance, ResourceMetric
    
    if settings.DEBUG:
        # 개발 환경인 경우
        Base.metadata.create_all(bind=engine)
        logger.info("All database tables created")
    else:
        # 개발 환경이 아닌 경우
        # TODO: 원래는 pass해야 함, 하지만 데모를 위해 강제로 생성. 나중에 제거 필요.
        Base.metadata.create_all(bind=engine)
        logger.info("All database tables created")


def check_database_connection() -> bool:
    """
    데이터베이스 연결 상태 확인
    헬스체크에서 사용
    """
    try:
        with engine.connect() as connection:
            connection.execute("SELECT 1")
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
            return connection.execute(query, params or {})

    def health_check(self) -> dict:
        """데이터베이스 헬스체크"""
        try:
            with self.engine.connect() as connection:
                result = connection.execute("SELECT version()").fetchone()
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