"""
db_manager.py
=============
AWS EC2 MySQL(MariaDB) 데이터베이스 연결을 관리하는 모듈.
pymysql 라이브러리를 사용하여 DB 연결/해제 및 쿼리 실행을 담당한다.
"""

import pymysql
from pymysql.cursors import DictCursor


class DatabaseManager:
    """
    MySQL/MariaDB 데이터베이스 연결을 관리하는 클래스.

    - 연결(connect) / 해제(disconnect) 기능 제공
    - 조회 결과를 딕셔너리(dict) 형태로 반환
    - 컨텍스트 매니저(with문) 지원
    """

    # ──────────────────────────────────────────────
    #  DB 접속 정보 (팀 전용 Private 레포 – 하드코딩)
    # ──────────────────────────────────────────────
    DB_CONFIG = {
        "host": "3.35.24.94",
        "user": "root",
        "password": "Sung!10292748",
        "database": "smart_farm_v2",
        "charset": "utf8mb4",           # 한글 등 멀티바이트 문자 안전 처리
        "cursorclass": DictCursor,       # 조회 결과를 딕셔너리로 반환
    }

    def __init__(self):
        """DatabaseManager 초기화. 연결 객체를 None으로 세팅."""
        self.connection = None

    # ──────────── 연결 ────────────
    def connect(self):
        """
        DB에 연결을 시도한다.
        성공 시 connection 객체를 저장하고, 실패 시 에러 메시지를 출력한다.
        """
        try:
            self.connection = pymysql.connect(**self.DB_CONFIG)
            print("=" * 50)
            print("✅ [DB 연결 성공] AWS EC2 MySQL 서버에 연결되었습니다.")
            print(f"   Host : {self.DB_CONFIG['host']}")
            print(f"   DB   : {self.DB_CONFIG['database']}")
            print("=" * 50)
        except pymysql.MySQLError as e:
            print("=" * 50)
            print(f"❌ [DB 연결 실패] 오류 코드: {e.args[0]}")
            print(f"   오류 메시지 : {e.args[1]}")
            print("=" * 50)
            self.connection = None

    # ──────────── 해제 ────────────
    def disconnect(self):
        """
        DB 연결을 안전하게 해제한다.
        이미 연결이 없는 경우에도 에러 없이 처리된다.
        """
        if self.connection and self.connection.open:
            self.connection.close()
            print("🔌 [DB 연결 해제] 데이터베이스 연결이 종료되었습니다.")
        else:
            print("ℹ️  이미 연결이 해제된 상태입니다.")

    # ──────────── 쿼리 실행 (SELECT) ────────────
    def execute_query(self, query: str, params: tuple = None) -> list[dict] | None:
        """
        SELECT 쿼리를 실행하고 결과를 딕셔너리 리스트로 반환한다.

        Args:
            query  : 실행할 SQL 쿼리 문자열
            params : 쿼리 파라미터 (SQL Injection 방지용)

        Returns:
            조회 결과 리스트(dict) 또는 실패 시 None
        """
        if not self.connection or not self.connection.open:
            print("⚠️  DB에 연결되어 있지 않습니다. 먼저 connect()를 호출하세요.")
            return None

        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query, params)
                result = cursor.fetchall()
                return result
        except pymysql.MySQLError as e:
            print(f"❌ [쿼리 실행 오류] {e}")
            return None

    # ──────────── 쿼리 실행 (INSERT / UPDATE / DELETE) ────────────
    def execute_update(self, query: str, params: tuple = None) -> int:
        """
        INSERT / UPDATE / DELETE 등 변경 쿼리를 실행하고 영향받은 행 수를 반환한다.

        Args:
            query  : 실행할 SQL 쿼리 문자열
            params : 쿼리 파라미터

        Returns:
            영향받은 행(row) 수. 실패 시 -1
        """
        if not self.connection or not self.connection.open:
            print("⚠️  DB에 연결되어 있지 않습니다. 먼저 connect()를 호출하세요.")
            return -1

        try:
            with self.connection.cursor() as cursor:
                affected_rows = cursor.execute(query, params)
                self.connection.commit()  # 변경 사항 커밋
                return affected_rows
        except pymysql.MySQLError as e:
            print(f"❌ [쿼리 실행 오류] {e}")
            self.connection.rollback()    # 오류 발생 시 롤백
            return -1

    # ──────────── 컨텍스트 매니저 지원 ────────────
    def __enter__(self):
        """with 문 진입 시 자동으로 DB에 연결한다."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """with 문 종료 시 자동으로 DB 연결을 해제한다."""
        self.disconnect()
