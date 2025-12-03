"""
초기 관리자 사용자 생성 스크립트
"""

from app.core.database import SessionLocal
from app.models.user import User, UserRole
from sqlalchemy.exc import IntegrityError

def create_initial_users():
    db = SessionLocal()
    try:
        # 1. Admin 생성
        admin_user = db.query(User).filter(User.hashed_password == "ADMIN").first()
        if not admin_user:
            admin_user = User(
                name="Admin",
                hashed_password="ADMIN",
                role=UserRole.ADMIN,
                is_active=True,
                created_by=None
            )
            db.add(admin_user)
            db.flush()  # admin_user.id를 얻기 위해 flush, test_user 생성 시 필요
            print("✅ Admin 생성: 접속 코드 'ADMIN'")
        else:
            print("ℹ️  Admin 이미 존재")

        # 2. 일반 사용자 생성
        user = db.query(User).filter(User.hashed_password == "USER1").first()
        if not user:
            user = User(
                name="Test User",
                hashed_password="USER1",
                role=UserRole.USER,
                is_active=True,
                created_by=admin_user.id  # Admin이 생성
            )
            db.add(user)
            print("✅ Test User 생성: 접속 코드 'USER1'")
        else:
            print("ℹ️  Test User 이미 존재")

        db.commit()
        print("\n🎉 초기 사용자 생성 완료!")
        print("\n사용 가능한 접속 코드:")
        print("  - ADMIN (Admin)")
        print("  - USER1 (User)")

    except IntegrityError as e:
        db.rollback()
        print(f"❌ 오류: {e}")
    except Exception as e:
        db.rollback()
        print(f"❌ 예상치 못한 오류: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    create_initial_users()
