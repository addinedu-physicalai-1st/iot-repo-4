"""
farm_repository.py
==================
farm_nodes / seedling_varieties 테이블과 통신하는 데이터 접근 계층(Repository).
DatabaseManager를 주입받아 SQL 쿼리를 실행한다.

참조 스키마: docs/DB_SCHEMA.md § 2. 농장 구역 및 품종
  - farm_nodes.node_id : VARCHAR(50) – PK
  - seedling_varieties.variety_id : INT – PK
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
    def get_node_by_id(self, node_id: str) -> dict | None:
        """
        특정 노드 ID에 해당하는 노드 정보를 조회한다.

        Args:
            node_id : 조회할 노드 ID (VARCHAR(50), 예: 'NODE-A1-001')

        Returns:
            노드 정보 딕셔너리 또는 None
        """
        query = "SELECT * FROM farm_nodes WHERE node_id = %s;"
        result = self.db.execute_query(query, (node_id,))

        if result:
            return result[0]  # 단일 행 반환
        return None

    # ──────────── 노드 환경 데이터 업데이트 ────────────
    def update_node_quantity(self, node_id: str, quantity: int) -> bool:
        """
        특정 노드의 현재 적재 수량을 업데이트한다.

        Args:
            node_id  : 업데이트할 노드 ID (VARCHAR(50))
            quantity : 변경할 적재 수량

        Returns:
            업데이트 성공 여부 (True/False)
        """
        query = """
            UPDATE farm_nodes
            SET current_quantity = %s
            WHERE node_id = %s;
        """
        affected = self.db.execute_update(query, (quantity, node_id))

        if affected > 0:
            print(f"✅ [FarmRepository] 노드 {node_id} 적재 수량 → {quantity}")
            return True
        else:
            print(f"⚠️ [FarmRepository] 노드 {node_id} 수량 업데이트 실패")
            return False

    # ──────────── 노드 상태(점유/비어있음) 업데이트 ────────────
    def update_node_variety(self, node_id: str, variety_id: int | None) -> bool:
        """
        노드에 품종을 배정하거나 초기화(출고 완료)한다.

        Args:
            node_id    : 대상 노드 ID (VARCHAR(50))
            variety_id : 배정할 품종 ID (None이면 비움 – 출고 완료 SR-38)

        Returns:
            업데이트 성공 여부
        """
        query = """
            UPDATE farm_nodes
            SET current_variety_id = %s
            WHERE node_id = %s;
        """
        affected = self.db.execute_update(query, (variety_id, node_id))
        return affected > 0

    # ──────────── 빈 적재 공간 검색 ────────────
    def find_empty_slots(self, node_type: str = "STATION") -> list[dict]:
        """
        현재 비어있는 (current_quantity < max_capacity) 저장고 노드를 반환한다.
        (SR-16: 빈 저장고 탐색)

        Args:
            node_type : 필터링할 노드 타입 (기본: 'STATION')

        Returns:
            비어있는 노드 딕셔너리 리스트 (없으면 빈 리스트)
        """
        query = """
            SELECT * FROM farm_nodes
            WHERE node_type = %s
              AND is_active = TRUE
              AND (current_quantity < max_capacity OR current_quantity IS NULL)
            ORDER BY node_id;
        """
        result = self.db.execute_query(query, (node_type,))

        if result:
            print(f"🔍 [FarmRepository] 빈 슬롯 {len(result)}건 발견")
        else:
            print("🔍 [FarmRepository] 빈 슬롯 없음")
            result = []

        return result

    # ──────────── 센서 로그 기록 ────────────
    def get_variety_by_id(self, variety_id: int) -> dict | None:
        """
        품종 ID로 seedling_varieties 테이블에서 품종 정보를 조회한다.

        Args:
            variety_id : 품종 고유 ID

        Returns:
            품종 정보 딕셔너리 또는 None
        """
        query = "SELECT * FROM seedling_varieties WHERE variety_id = %s;"
        result = self.db.execute_query(query, (variety_id,))
        return result[0] if result else None

    def find_section_for_variety(self, variety_id: int) -> list[dict]:
        """
        특정 품종이 배정될 수 있는 섹션(노드) 목록을 조회한다.
        (SR-15: 품종에 맞는 섹션 배정)

        Args:
            variety_id : 배정할 품종 ID

        Returns:
            해당 품종에 맞는 빈 노드 리스트
        """
        query = """
            SELECT * FROM farm_nodes
            WHERE node_type = 'STATION'
              AND is_active = TRUE
              AND (current_variety_id = %s OR current_variety_id IS NULL)
              AND (current_quantity < max_capacity OR current_quantity IS NULL)
            ORDER BY node_id;
        """
        result = self.db.execute_query(query, (variety_id,))
        return result if result else []
