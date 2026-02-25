"""
agv_repository.py
=================
AGV(무인 운반차) 및 운송 작업 테이블과 통신하는 데이터 접근 계층(Repository).

참조 스키마: docs/DB_SCHEMA.md § 3. 무인 운반차 (AGV)
  - agv_robots           : AGV 마스터
  - transport_tasks      : 운송 지시 작업
  - agv_telemetry_logs   : 주행 로그
  - agv_search_logs      : 작업 로그
"""

from database.db_manager import DatabaseManager


class AgvRepository:
    """
    AGV 관련 테이블에 대한 CRUD 연산을 담당하는 레포지토리 클래스.

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
    #  agv_robots 테이블
    # ============================================================

    def get_agv_by_id(self, agv_id: str) -> dict | None:
        """AGV ID로 기체 정보를 조회한다."""
        query = "SELECT * FROM agv_robots WHERE agv_id = %s;"
        result = self.db.execute_query(query, (agv_id,))
        return result[0] if result else None

    def get_all_agvs(self) -> list[dict]:
        """전체 AGV 목록을 조회한다."""
        query = "SELECT * FROM agv_robots ORDER BY agv_id;"
        result = self.db.execute_query(query)
        return result if result else []

    def update_agv_status(self, agv_id: str, status: str, battery: int = None) -> bool:
        """
        AGV의 현재 상태와 배터리를 업데이트한다.

        Args:
            agv_id  : AGV 식별 ID (VARCHAR(20))
            status  : 변경할 상태 ('IDLE','MOVING','WORKING','CHARGING','ERROR')
            battery : 배터리 잔량 (None이면 갱신 안 함)
        """
        if battery is not None:
            query = """
                UPDATE agv_robots
                SET current_status = %s,
                    battery_level = %s,
                    last_ping = NOW()
                WHERE agv_id = %s;
            """
            affected = self.db.execute_update(query, (status, battery, agv_id))
        else:
            query = """
                UPDATE agv_robots
                SET current_status = %s,
                    last_ping = NOW()
                WHERE agv_id = %s;
            """
            affected = self.db.execute_update(query, (status, agv_id))

        return affected > 0

    def update_agv_ping(self, agv_id: str) -> bool:
        """AGV의 last_ping을 현재 시각으로 갱신한다 (하트비트)."""
        query = "UPDATE agv_robots SET last_ping = NOW() WHERE agv_id = %s;"
        return self.db.execute_update(query, (agv_id,)) > 0

    # ============================================================
    #  transport_tasks 테이블
    # ============================================================

    def create_transport_task(
        self,
        agv_id: str,
        variety_id: int,
        source_node: str,
        destination_node: str,
        ordered_by: int,
        quantity: int = 1,
    ) -> int:
        """
        새로운 운송 작업을 DB에 생성한다.

        Returns:
            생성된 task_id 또는 실패 시 -1
        """
        query = """
            INSERT INTO transport_tasks
                (agv_id, variety_id, source_node, destination_node,
                 ordered_by, quantity, task_status, ordered_at)
            VALUES (%s, %s, %s, %s, %s, %s, 'PENDING', NOW());
        """
        affected = self.db.execute_update(
            query, (agv_id, variety_id, source_node, destination_node, ordered_by, quantity)
        )
        if affected > 0:
            # 마지막 INSERT ID 조회
            result = self.db.execute_query("SELECT LAST_INSERT_ID() AS task_id;")
            return result[0]["task_id"] if result else -1
        return -1

    def update_task_status(self, task_id: int, status: str) -> bool:
        """
        운송 작업의 상태를 변경한다.

        Args:
            task_id : 작업 고유 ID
            status  : 'PENDING','IN_PROGRESS','COMPLETED','FAILED'
        """
        # 완료 시 completed_at도 함께 갱신
        if status == "COMPLETED":
            query = """
                UPDATE transport_tasks
                SET task_status = %s, completed_at = NOW()
                WHERE task_id = %s;
            """
        elif status == "IN_PROGRESS":
            query = """
                UPDATE transport_tasks
                SET task_status = %s, started_at = NOW()
                WHERE task_id = %s;
            """
        else:
            query = """
                UPDATE transport_tasks
                SET task_status = %s
                WHERE task_id = %s;
            """
        return self.db.execute_update(query, (status, task_id)) > 0

    def get_pending_tasks(self) -> list[dict]:
        """대기 중인 운송 작업 목록을 조회한다 (우선순위: 출고 먼저)."""
        query = """
            SELECT * FROM transport_tasks
            WHERE task_status = 'PENDING'
            ORDER BY ordered_at ASC;
        """
        result = self.db.execute_query(query)
        return result if result else []

    def get_task_by_id(self, task_id: int) -> dict | None:
        """특정 운송 작업을 ID로 조회한다."""
        query = "SELECT * FROM transport_tasks WHERE task_id = %s;"
        result = self.db.execute_query(query, (task_id,))
        return result[0] if result else None

    # ============================================================
    #  agv_telemetry_logs / agv_search_logs 테이블
    # ============================================================

    def insert_telemetry_log(self, agv_id: str, task_id: int = None) -> bool:
        """AGV 주행 로그를 기록한다."""
        query = """
            INSERT INTO agv_telemetry_logs (agv_id, task_id, logged_at)
            VALUES (%s, %s, NOW());
        """
        return self.db.execute_update(query, (agv_id, task_id)) > 0

    def insert_search_log(self, agv_id: str, task_id: int, motor_angle: int = 0) -> bool:
        """AGV 작업(서보 모터 동작) 로그를 기록한다."""
        query = """
            INSERT INTO agv_search_logs (agv_id, task_id, current_motor, logged_at)
            VALUES (%s, %s, %s, NOW());
        """
        return self.db.execute_update(query, (agv_id, task_id, motor_angle)) > 0
