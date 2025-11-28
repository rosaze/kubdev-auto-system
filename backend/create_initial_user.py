"""
초기 관리자 사용자 생성 스크립트
"""

from app.core.database import SessionLocal
from app.models.user import User, UserRole
from sqlalchemy.exc import IntegrityError

def create_initial_users():
    db = SessionLocal()
    try:
        # 1. Super Admin 생성
        admin_user = db.query(User).filter(User.hashed_password == "ADMIN").first()
        if not admin_user:
            admin_user = User(
                name="Super Admin",
                hashed_password="ADMIN",  # 접속 코드
                role=UserRole.SUPER_ADMIN,
                is_active=True,
                is_verified=True
            )
            db.add(admin_user)
            print("✅ Super Admin 생성: 접속 코드 'ADMIN'")
        else:
            print("ℹ️  Super Admin 이미 존재")

        # 2. 테스트 개발자 생성
        dev_user = db.query(User).filter(User.hashed_password == "DEV01").first()
        if not dev_user:
            dev_user = User(
                name="Test Developer",
                hashed_password="DEV01",  # 접속 코드
                role=UserRole.DEVELOPER,
                is_active=True,
                is_verified=True
            )
            db.add(dev_user)
            print("✅ Test Developer 생성: 접속 코드 'DEV01'")
        else:
            print("ℹ️  Test Developer 이미 존재")

        # 3. 조직 관리자 생성
        org_admin = db.query(User).filter(User.hashed_password == "ORG01").first()
        if not org_admin:
            org_admin = User(
                name="Organization Admin",
                hashed_password="ORG01",  # 접속 코드
                role=UserRole.ORG_ADMIN,
                is_active=True,
                is_verified=True
            )
            db.add(org_admin)
            print("✅ Organization Admin 생성: 접속 코드 'ORG01'")
        else:
            print("ℹ️  Organization Admin 이미 존재")

        db.commit()
        print("\n🎉 초기 사용자 생성 완료!")
        print("\n사용 가능한 접속 코드:")
        print("  - ADMIN (Super Admin)")
        print("  - DEV01 (Developer)")
        print("  - ORG01 (Organization Admin)")

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
