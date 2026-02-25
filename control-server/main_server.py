"""
main_server.py
==============
통합 스마트팜 자동화 시스템 – 중앙 제어 서버 진입점(Entry Point).
AWS EC2 MySQL 서버와의 연결 테스트를 수행한다.
"""

from database.db_manager import DatabaseManager


def main():
    """
    메인 함수:
    1) DatabaseManager를 통해 EC2 MySQL에 연결
    2) SELECT VERSION() 쿼리로 DB 버전 확인
    3) smart_farm_v2 DB의 테이블 목록 조회
    4) DB 연결 해제
    """
    print()
    print("🌱 ======================================== 🌱")
    print("   통합 스마트팜 자동화 시스템 – 서버 시작")
    print("🌱 ======================================== 🌱")
    print()

    # ── DatabaseManager를 컨텍스트 매니저로 사용 ──
    with DatabaseManager() as db:

        # 연결 실패 시 조기 종료
        if db.connection is None:
            print("🚫 DB 연결에 실패하여 서버를 종료합니다.")
            return

        # ─── 테스트 1: DB 서버 버전 확인 ───
        print("\n📌 [테스트 1] DB 서버 버전 확인")
        print("-" * 40)
        version_result = db.execute_query("SELECT VERSION() AS db_version;")
        if version_result:
            print(f"   DB 버전: {version_result[0]['db_version']}")
        else:
            print("   ⚠️ 버전 정보를 가져오지 못했습니다.")

        # ─── 테스트 2: 현재 DB의 테이블 목록 조회 ───
        print("\n📌 [테스트 2] '{0}' 데이터베이스 테이블 목록".format(
            DatabaseManager.DB_CONFIG["database"]
        ))
        print("-" * 40)
        tables = db.execute_query("SHOW TABLES;")
        if tables:
            for idx, table in enumerate(tables, start=1):
                # SHOW TABLES 결과의 키는 'Tables_in_<db명>' 형태
                table_name = list(table.values())[0]
                print(f"   {idx}. {table_name}")
            print(f"\n   총 {len(tables)}개의 테이블이 조회되었습니다. ✅")
        else:
            print("   ⚠️ 테이블 목록을 가져오지 못했습니다.")

    # with 블록 종료 → 자동으로 disconnect() 호출
    print("\n🏁 서버 종료. 모든 테스트가 완료되었습니다.\n")


if __name__ == "__main__":
    main()
