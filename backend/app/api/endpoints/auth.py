"""
Authentication API Endpoints (New)
user_id 기반 인증 API
"""
import structlog
from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session
from datetime import datetime

from app.core.database import get_db
from app.models.user import User
from app.schemas.user import (
    UserLogin,
    UserLoginResponse,
    UserLogout
)

router = APIRouter()
log = structlog.get_logger(__name__)


@router.post("/login", response_model=UserLoginResponse)
async def login(
    login_data: UserLogin,
    db: Session = Depends(get_db)
):
    """접속 코드로 로그인"""
    log.info("Login attempt", access_code=login_data.access_code)
    
    # 접속 코드로 사용자 찾기
    user = db.query(User).filter(User.hashed_password == login_data.access_code).first()
    
    if not user:
        log.warning("Login failed: invalid access code", access_code=login_data.access_code)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access code"
        )

    if not user.is_active:
        log.warning("Login failed: inactive user", access_code=login_data.access_code, user_id=user.id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )

    # 마지막 로그인 시간 업데이트
    user.last_login_at = datetime.utcnow()
    db.commit()
    db.refresh(user)

    log.info("Login successful", user_id=user.id, user_name=user.name)

    # 사용자 정보 반환
    user_info = UserLoginResponse.UserInfo(
        id=user.id,
        name=user.name,
        role=user.role,
        last_login=user.last_login_at
    )

    return UserLoginResponse(user_info=user_info)


@router.post("/logout")
async def logout(
    logout_data: UserLogout,
    db: Session = Depends(get_db)
):
    """사용자 로그아웃"""
    log.info("User logout requested", user_id=logout_data.user_id)
    
    # 사용자 존재 확인
    user = db.query(User).filter(User.id == logout_data.user_id).first()
    if not user:
        log.warning("Logout failed: user not found", user_id=logout_data.user_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    log.info("User logged out", user_id=user.id, user_name=user.name)
    
    return {"message": "로그아웃 성공"}
