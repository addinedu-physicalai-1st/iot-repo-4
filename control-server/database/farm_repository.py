"""
farm_repository.py
==================
farm_nodes 테이블과 통신하는 데이터 접근 계층(Repository).
DatabaseManager를 주입받아 SQL 쿼리를 실행한다.
"""

from database.db_manager import DatabaseManager


class FarmRepository:
    """
    스마트팜 노드(farm_nodes) 테이블에 대한 CRUD 연산을 담당하는 레포지토리 클래스.

    역할:
        - 특정 노드의 상태(온도, 습도, 작물 존재 여부 등) 조회 / 업데이트
        - 빈 적재 공간(비어있는 슬롯) 검색
        - 센서 로그 기록

    의존성:
        - DatabaseManager : DB 연결 및 쿼리 실행 담당
    """

    def __init__(self, db_manager: DatabaseManager):
        """
        Args:
            db_manager : DatabaseManager 인스턴스 (DI – 의존성 주입)
        """
        self.db = db_manager

    # ──────────── 노드 전체 목록 조회 ────────────
    def get_all_nodes(self) -> list[dict] | None:
        """
        farm_nodes 테이블의 전체 노드 목록을 조회한다.

        Returns:
            노드 딕셔너리 리스트 또는 None
        """
        query = "SELECT * FROM farm_nodes;"
        result = self.db.execute_query(query)

        if result:
            print(f"📋 [FarmRepository] 전체 노드 {len(result)}건 조회 완료")
        else:
            print("⚠️ [FarmRepository] 노드 목록 조회 실패 또는 데이터 없음")

        return result

    # ──────────── 특정 노드 상태 조회 ────────────
    def get_node_by_id(self, node_id: int) -> dict | None:
        """
        특정 노드 ID에 해당하는 노드 정보를 조회한다.

        Args:
            node_id : 조회할 노드 ID

        Returns:
            노드 정보 딕셔너리 또는 None
        """
        query = "SELECT * FROM farm_nodes WHERE node_id = %s;"
        result = self.db.execute_query(query, (node_id,))

        if result:
            return result[0]  # 단일 행 반환
        return None

    # ──────────── 노드 환경 데이터 업데이트 ────────────
    def update_node_environment(self, node_id: int, temperature: float, humidity: float) -> bool:
        """
        특정 노드의 현재 온도/습도 값을 업데이트한다.

        Args:
            node_id     : 업데이트할 노드 ID
            temperature : 현재 온도 (°C)
            humidity    : 현재 습도 (%)

        Returns:
            업데이트 성공 여부 (True/False)
        """
        # TODO: 실제 테이블 컬럼명에 맞게 쿼리를 수정할 것
        query = """
            UPDATE farm_nodes
            SET temperature = %s,
                humidity = %s,
                updated_at = NOW()
            WHERE node_id = %s;
        """
        affected = self.db.execute_update(query, (temperature, humidity, node_id))

        if affected > 0:
            print(f"✅ [FarmRepository] 노드 {node_id} 환경 데이터 업데이트 완료 "
                  f"(온도={temperature}°C, 습도={humidity}%)")
            return True
        else:
            print(f"⚠️ [FarmRepository] 노드 {node_id} 업데이트 실패")
            return False

    # ──────────── 노드 상태(점유/비어있음) 업데이트 ────────────
    def update_node_status(self, node_id: int, status: str) -> bool:
        """
        노드의 점유 상태를 변경한다. (예: 'empty', 'occupied', 'growing')

        Args:
            node_id : 대상 노드 ID
            status  : 변경할 상태 문자열

        Returns:
            업데이트 성공 여부
        """
        # TODO: 실제 status 컬럼명에 맞게 쿼리를 수정할 것
        query = """
            UPDATE farm_nodes
            SET status = %s,
                updated_at = NOW()
            WHERE node_id = %s;
        """
        affected = self.db.execute_update(query, (status, node_id))
        return affected > 0

    # ──────────── 빈 적재 공간 검색 ────────────
    def find_empty_slots(self) -> list[dict]:
        """
        현재 비어있는(status='empty') 노드 슬롯 목록을 반환한다.
        로봇이 작물을 이송할 목적지를 결정할 때 사용된다.

        Returns:
            비어있는 노드 딕셔너리 리스트 (없으면 빈 리스트)
        """
        # TODO: 실제 status 값이 다를 경우 WHERE 조건 수정
        query = "SELECT * FROM farm_nodes WHERE status = 'empty';"
        result = self.db.execute_query(query)

        if result:
            print(f"🔍 [FarmRepository] 빈 슬롯 {len(result)}건 발견")
        else:
            print("🔍 [FarmRepository] 빈 슬롯 없음")
            result = []

        return result

    # ──────────── 센서 로그 기록 ────────────
    def insert_sensor_log(self, node_id: int, temperature: float, humidity: float) -> bool:
        """
        센서에서 수신된 환경 데이터를 로그 테이블에 기록한다.

        Args:
            node_id     : 센서가 설치된 노드 ID
            temperature : 측정 온도
            humidity    : 측정 습도

        Returns:
            기록 성공 여부
        """
        # TODO: sensor_logs 테이블이 존재해야 함. 컬럼명 확인 후 수정.
        query = """
            INSERT INTO sensor_logs (node_id, temperature, humidity, logged_at)
            VALUES (%s, %s, %s, NOW());
        """
        affected = self.db.execute_update(query, (node_id, temperature, humidity))
        return affected > 0
