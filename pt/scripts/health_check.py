import sys
from pathlib import Path

# 프로젝트 경로 추가
sys.path.append(str(Path("/home/ubuntu/pt_system")))
sys.path.append(str(Path(__file__).resolve().parents[1]))

from scripts.db import get_conn

def check_health():
    try:
        conn = get_conn()
        cursor = conn.cursor()
        
        # 테이블 존재 여부 확인
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        print(f"연동된 테이블: {[t[0] for t in tables]}")
        
        conn.close()
        print("시스템 상태: 정상 (데이터베이스 연결 완료)")
    except Exception as e:
        print(f"시스템 상태: 오류 발생 - {e}")

if __name__ == "__main__":
    check_health()