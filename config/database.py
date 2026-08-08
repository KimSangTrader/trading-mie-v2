"""
Database Configuration for MIE V2.0
PostgreSQL RDS 연결 설정
"""

import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text  # ← text 추가!
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

# .env 파일 로드
load_dotenv()

class DatabaseConfig:
    """데이터베이스 설정 클래스"""
    
    # 환경 설정
    ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')
    
    # 개발 환경 (로컬 SQLite - 선택사항)
    DEVELOPMENT_DB_URL = "sqlite:///./mie_v2_dev.db"
    
    # 프로덕션 환경 (AWS RDS PostgreSQL)
    PRODUCTION_DB_URL = (
        f"postgresql://"
        f"{os.getenv('RDS_USERNAME', 'mieadmin')}:"
        f"{os.getenv('RDS_PASSWORD', 'MieV2Postgres2026!')}@"
        f"{os.getenv('RDS_HOST', 'localhost')}:"
        f"{os.getenv('RDS_PORT', '5432')}/"
        f"{os.getenv('RDS_DATABASE', 'postgres')}"
    )
    
    @classmethod
    def get_database_url(cls) -> str:
        """환경에 맞는 데이터베이스 URL 반환"""
        if cls.ENVIRONMENT == 'production':
            return cls.PRODUCTION_DB_URL
        else:
            return cls.DEVELOPMENT_DB_URL
    
    @classmethod
    def get_engine_config(cls) -> dict:
        """SQLAlchemy 엔진 설정"""
        config = {
            'echo': False,
            'pool_pre_ping': True,  # 연결 검증
            'pool_recycle': 3600,   # 1시간마다 연결 재활용
        }
        
        if cls.ENVIRONMENT == 'production':
            config.update({
                'pool_size': 10,
                'max_overflow': 20,
                'connect_args': {
                    'connect_timeout': 10,
                },
            })
        else:
            config.update({
                'pool_size': 5,
                'max_overflow': 10,
            })
        
        return config

# ==========================================
# 데이터베이스 엔진 및 세션 설정
# ==========================================

# 데이터베이스 URL 가져오기
DATABASE_URL = DatabaseConfig.get_database_url()

# 엔진 설정
ENGINE_CONFIG = DatabaseConfig.get_engine_config()

# SQLAlchemy 엔진 생성
engine = create_engine(
    DATABASE_URL,
    **ENGINE_CONFIG
)

# 세션 팩토리 생성
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# ==========================================
# 세션 의존성 함수 (FastAPI용)
# ==========================================

def get_db() -> Generator[Session, None, None]:
    """
    데이터베이스 세션 반환 (의존성 주입)
    
    FastAPI에서 사용:
    @app.get("/data")
    def get_data(db: Session = Depends(get_db)):
        ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ==========================================
# 데이터베이스 초기화 함수
# ==========================================

def init_db():
    """
    데이터베이스 초기화
    모든 테이블 생성
    """
    from db.models import Base
    
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("✅ Database tables created successfully!")

def drop_db():
    """
    데이터베이스 초기화 (개발용)
    모든 테이블 삭제
    """
    from db.models import Base
    
    print("⚠️  Dropping all tables...")
    Base.metadata.drop_all(bind=engine)
    print("✅ All tables dropped!")

def test_connection():
    """
    데이터베이스 연결 테스트
    """
    try:
        db = SessionLocal()
        # 간단한 쿼리 실행
        result = db.execute(text("SELECT 1"))
        db.close()
        print("✅ Database connection successful!")
        return True
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False

# ==========================================
# 데이터베이스 정보 출력
# ==========================================

def print_db_info():
    """데이터베이스 설정 정보 출력 (디버깅용)"""
    print("\n" + "="*50)
    print("Database Configuration")
    print("="*50)
    print(f"Environment: {DatabaseConfig.ENVIRONMENT}")
    print(f"Database URL: {DATABASE_URL.replace(os.getenv('RDS_PASSWORD', 'MieV2Postgres2026!'), '****')}")
    print(f"Pool Size: {ENGINE_CONFIG.get('pool_size', 'N/A')}")
    print(f"Max Overflow: {ENGINE_CONFIG.get('max_overflow', 'N/A')}")
    print("="*50 + "\n")

# ==========================================
# 모듈 실행 시 (테스트)
# ==========================================

if __name__ == "__main__":
    print_db_info()
    if test_connection():
        print("✅ Ready to use!")
    else:
        print("❌ Please check your database configuration.")