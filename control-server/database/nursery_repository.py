"""
nursery_repository.py
=====================
육묘장 환경 제어 관련 테이블과 통신하는 데이터 접근 계층(Repository).

참조 스키마: docs/DB_SCHEMA.md § 4. 육묘장 환경 제어
  - nursery_controller     : 제어기 마스터
  - nursery_sensor         : 센서 마스터
  - nursery_sensor_logs    : 센서 수집 로그
  - nursery_actuator_logs  : 구동기 제어 로그
"""

from database.db_manager import DatabaseManager


class NurseryRepository:
    """
    육묘장 제어기·센서·액추에이터 테이블에 대한 CRUD 연산을 담당하는 레포지토리.

    의존성:
        - DatabaseManager : DB 연결 및 쿼리 실행 담당
    """

    def __init__(self, db_manager: DatabaseManager):
        """
        Args:
            db_manager : DatabaseManager 인스턴스 (DI)
        """
        self.db = db_manager

    # ============================================================
    #  nursery_controller 테이블
    # ============================================================

    def get_controller_by_id(self, controller_id: str) -> dict | None:
        """제어기 ID로 제어기 정보를 조회한다."""
        query = "SELECT * FROM nursery_controller WHERE controller_id = %s;"
        result = self.db.execute_query(query, (controller_id,))
        return result[0] if result else None

    def get_controllers_by_node(self, node_id: str) -> list[dict]:
        """특정 노드에 설치된 제어기 목록을 조회한다."""
        query = "SELECT * FROM nursery_controller WHERE node_id = %s;"
        result = self.db.execute_query(query, (node_id,))
        return result if result else []

    def get_all_online_controllers(self) -> list[dict]:
        """ONLINE 상태인 전체 제어기 목록을 조회한다."""
        query = """
            SELECT * FROM nursery_controller
            WHERE device_status = 'ONLINE'
            ORDER BY controller_id;
        """
        result = self.db.execute_query(query)
        return result if result else []

    def update_controller_mode(self, controller_id: str, mode: str) -> bool:
        """
        제어기의 동작 모드를 변경한다. (SR-29: 수동/자동 전환)

        Args:
            controller_id : 제어기 ID (VARCHAR(50))
            mode          : 'AUTO' 또는 'MANUAL'
        """
        query = """
            UPDATE nursery_controller
            SET control_mode = %s
            WHERE controller_id = %s;
        """
        return self.db.execute_update(query, (mode, controller_id)) > 0

    def update_controller_status(self, controller_id: str, status: str) -> bool:
        """제어기의 통신 상태를 변경한다 ('ONLINE'/'OFFLINE')."""
        query = """
            UPDATE nursery_controller
            SET device_status = %s, last_heartbeat = NOW()
            WHERE controller_id = %s;
        """
        return self.db.execute_update(query, (status, controller_id)) > 0

    def update_heartbeat(self, controller_id: str) -> bool:
        """제어기의 마지막 통신 시간을 갱신한다."""
        query = """
            UPDATE nursery_controller
            SET last_heartbeat = NOW()
            WHERE controller_id = %s;
        """
        return self.db.execute_update(query, (controller_id,)) > 0

    # ============================================================
    #  nursery_sensor 테이블
    # ============================================================

    def get_sensors_by_controller(self, controller_id: str) -> list[dict]:
        """특정 제어기에 연결된 센서 목록을 조회한다."""
        query = "SELECT * FROM nursery_sensor WHERE controller_id = %s;"
        result = self.db.execute_query(query, (controller_id,))
        return result if result else []

    # ============================================================
    #  nursery_sensor_logs 테이블
    # ============================================================

    def insert_sensor_log(self, sensor_id: int, value: float) -> bool:
        """
        센서 측정값을 로그 테이블에 기록한다.

        Args:
            sensor_id : 센서 고유 ID
            value     : 실제 측정값 (DECIMAL(10,2))
        """
        query = """
            INSERT INTO nursery_sensor_logs (sensor_id, value, measured_at)
            VALUES (%s, %s, NOW());
        """
        return self.db.execute_update(query, (sensor_id, value)) > 0

    def get_recent_sensor_logs(self, sensor_id: int, limit: int = 10) -> list[dict]:
        """특정 센서의 최근 로그를 조회한다."""
        query = """
            SELECT * FROM nursery_sensor_logs
            WHERE sensor_id = %s
            ORDER BY measured_at DESC
            LIMIT %s;
        """
        result = self.db.execute_query(query, (sensor_id, limit))
        return result if result else []

    # ============================================================
    #  nursery_actuator_logs 테이블
    # ============================================================

    def insert_actuator_log(
        self,
        actuator_id: int,
        state_value: str,
        triggered_by: str = "AUTO_LOGIC",
    ) -> bool:
        """
        액추에이터(팬, 히터, 가습기 등) 동작을 로그에 기록한다.

        Args:
            actuator_id  : 구동기 ID
            state_value  : 변경된 상태 ('ON', 'OFF' 등)
            triggered_by : 동작 원인 ('AUTO_LOGIC', 'MANUAL' 등)
        """
        query = """
            INSERT INTO nursery_actuator_logs
                (actuator_id, state_value, triggered_by, logged_at)
            VALUES (%s, %s, %s, NOW());
        """
        return self.db.execute_update(query, (actuator_id, state_value, triggered_by)) > 0
