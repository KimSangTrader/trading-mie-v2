import psycopg2
from psycopg2 import sql

# RDS 연결 정보
DB_CONFIG = {
    'host': 'mie-v2-db.c5sqesk6qyqd.ap-northeast-2.rds.amazonaws.com',
    'port': 5432,
    'user': 'mieadmin',
    'password': 'MieV2Postgres2026!',
    'database': 'postgres'
}

try:
    # 연결 시도
    print("RDS PostgreSQL 연결 시도 중...")
    conn = psycopg2.connect(**DB_CONFIG)
    
    # 커서 생성
    cur = conn.cursor()
    
    # 테스트 쿼리 실행
    print("✅ 연결 성공!")
    print()
    
    # 1. 버전 확인
    cur.execute("SELECT version();")
    db_version = cur.fetchone()
    print(f"PostgreSQL 버전: {db_version[0]}")
    print()
    
    # 2. 기본 쿼리 테스트
    cur.execute("SELECT 1 as test_value;")
    result = cur.fetchone()
    print(f"테스트 쿼리 결과: {result[0]}")
    print()
    
    # 3. 데이터베이스 목록 확인
    cur.execute("""
        SELECT datname FROM pg_database 
        WHERE datistemplate = false 
        ORDER BY datname;
    """)
    databases = cur.fetchall()
    print("생성된 데이터베이스:")
    for db in databases:
        print(f"  - {db[0]}")
    print()
    
    # 4. 현재 사용자 확인
    cur.execute("SELECT user;")
    current_user = cur.fetchone()
    print(f"현재 사용자: {current_user[0]}")
    print()
    
    # 5. 연결 정보 출력
    print("【연결 정보 확인】")
    print(f"호스트: {DB_CONFIG['host']}")
    print(f"포트: {DB_CONFIG['port']}")
    print(f"사용자: {DB_CONFIG['user']}")
    print(f"데이터베이스: {DB_CONFIG['database']}")
    print()
    
    print("✅ RDS PostgreSQL 연결 테스트 완료!")
    
    # 연결 종료
    cur.close()
    conn.close()
    
except (Exception, psycopg2.DatabaseError) as error:
    print(f"❌ 연결 실패!")
    print(f"오류: {error}")
    print()
    print("【확인 사항】")
    print("1. RDS 엔드포인트 주소 확인")
    print("2. 사용자명/암호 확인")
    print("3. 보안 그룹에서 포트 5432 허용 확인")
    print("4. RDS 상태 확인 ('사용 가능' 상태)")