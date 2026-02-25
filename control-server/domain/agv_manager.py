"""
agv_manager.py
==============
무인 운반차(AGV)의 상태(위치, 배터리, 동작 상태)를 추적하고,
TransportTaskQueue를 통해 운송 작업을 할당·관리하는 매니저 모듈.

참조 스키마: docs/DB_SCHEMA.md § 3. 무인 운반차 (AGV)
  - agv_robots.agv_id         : VARCHAR(20) – PK
  - agv_robots.current_status : ENUM ('IDLE','MOVING','WORKING','CHARGING','ERROR')
  - agv_robots.battery_level  : INT

SR 참조:
  - SR-07: 무인 이송 시스템 역할
  - SR-21~24: 주행 및 하역 프로세스
  - SR-39: 진행 중 명령 우선 처리
  - SR-41: 유휴 상태 배회 감시
"""

from enum import Enum
from domain.transport_task import TransportTaskQueue, TransportTask, TaskStatus


class AgvStatus(Enum):
    """AGV의 현재 동작 상태 (DB ENUM과 일치)"""
    IDLE = "IDLE"              # 대기 중
    MOVING = "MOVING"          # 이동 중
    WORKING = "WORKING"        # 작업 수행 중 (상하차 등)
    CHARGING = "CHARGING"      # 충전 중
    ERROR = "ERROR"            # 오류 상태
    PATROLLING = "PATROLLING"  # 유휴 배회 감시 (SR-41)


class AgvManager:
    """
    AGV(무인 운반차)의 실시간 상태를 관리하고, Task를 할당하는 매니저 클래스.

    추적 정보:
        - 현재 위치 (pos_x, pos_y) – 관제 UI 도면 좌표
        - 배터리 잔량 (%)
        - 동작 상태 (AgvStatus)
        - 현재 수행 중인 TransportTask

    의존성:
        - TransportTaskQueue : 작업 큐에서 Task를 가져와 할당
    """

    # 배터리가 이 값 이하이면 충전이 필요하다고 판단
    LOW_BATTERY_THRESHOLD = 20  # (%)

    def __init__(self, task_queue: TransportTaskQueue):
        """
        Args:
            task_queue : TransportTaskQueue 인스턴스 (DI – 의존성 주입)
        """
        self.task_queue = task_queue

        # ── AGV 상태 초기화 ──
        self.agv_id: str = ""                # AGV 식별 ID (VARCHAR(20))
        self.pos_x: int = 0                  # 현재 X 좌표
        self.pos_y: int = 0                  # 현재 Y 좌표
        self.battery_level: int = 100        # 배터리 잔량 (%)
        self.status: AgvStatus = AgvStatus.IDLE
        self.current_task: TransportTask | None = None  # 현재 수행 중인 Task

    # ──────────── AGV 상태 업데이트 ────────────
    def update_agv_status(self, agv_id: str, payload: dict):
        """
        네트워크에서 수신된 AGV 상태 정보를 반영한다.

        Args:
            agv_id  : AGV 식별 ID (VARCHAR(20), 예: "R01")
            payload : 상태 정보 딕셔너리
                      예: {"pos_x": 120, "pos_y": 350, "battery": 80, "status": "MOVING"}
        """
        self.agv_id = agv_id

        # 위치 정보 갱신
        if "pos_x" in payload:
            self.pos_x = payload["pos_x"]
        if "pos_y" in payload:
            self.pos_y = payload["pos_y"]

        # 배터리 정보 갱신
        if "battery" in payload:
            self.battery_level = payload["battery"]
            if self.battery_level <= self.LOW_BATTERY_THRESHOLD:
                print(f"🪫 [AgvManager] ⚠️ AGV {agv_id} 배터리 부족! "
                      f"({self.battery_level}%) → 충전 필요")

        # 상태 정보 갱신
        if "status" in payload:
            try:
                self.status = AgvStatus(payload["status"])
            except ValueError:
                print(f"⚠️ [AgvManager] 알 수 없는 상태값: {payload['status']}")

        print(f"🤖 [AgvManager] AGV {agv_id} 상태 갱신 → "
              f"위치=({self.pos_x}, {self.pos_y}), "
              f"배터리={self.battery_level}%, 상태={self.status.value}")

    # ──────────── Task 할당 ────────────
    def assign_next_task(self) -> TransportTask | None:
        """
        큐에서 우선순위가 가장 높은 Task를 꺼내 AGV에 할당한다.
        (SR-39: 진행 중 명령은 먼저 완료 후 할당)

        Returns:
            할당된 TransportTask 또는 None
        """
        # AGV가 이미 작업 중이면 새 Task 할당 불가 (SR-39)
        if self.status not in (AgvStatus.IDLE, AgvStatus.PATROLLING):
            print(f"⚠️ [AgvManager] AGV가 현재 '{self.status.value}' 상태입니다. "
                  f"IDLE 상태에서만 Task 할당 가능.")
            return None

        # 배터리 부족 시 Task 할당 거부
        if self.battery_level <= self.LOW_BATTERY_THRESHOLD:
            print(f"🪫 [AgvManager] 배터리 부족({self.battery_level}%)으로 Task 할당 불가.")
            return None

        # 큐에서 다음 Task 가져오기 (우선순위: 출고 > 입고)
        task = self.task_queue.get_next_task()
        if task:
            task.agv_id = self.agv_id
            self.current_task = task
            self.status = AgvStatus.MOVING
            print(f"✅ [AgvManager] Task [{task.task_id}] 할당 완료 → "
                  f"{task.task_type.label}: {task.source_node} → {task.destination_node}")

            # TODO: 실제로 AGV 펌웨어에 이동 명령을 전송하는 로직
            #   - TCP 소켓을 통해 ESP32에 JSON 명령 패킷 전송
            #   - {"cmd": "MOVE", "target_node": task.destination_node}
            self._send_command_to_agv(task)
        else:
            # 할당할 Task가 없으면 배회 상태로 전환 (SR-41)
            if self.status == AgvStatus.IDLE:
                print("ℹ️  [AgvManager] 할당할 Task 없음 → 유휴 대기")
                # TODO: 일정 시간 후 PATROLLING 상태로 전환

        return task

    # ──────────── 작업 결과 처리 ────────────
    def handle_task_result(self, agv_id: str, result: str):
        """
        AGV에서 수신한 작업 완료/실패 결과를 처리한다.

        Args:
            agv_id : AGV 식별 ID
            result : "SUCCESS" 또는 "FAIL"
        """
        if result == "SUCCESS":
            print(f"🎉 [AgvManager] AGV {agv_id} Task 성공!")
            if self.current_task:
                self.current_task.status = TaskStatus.COMPLETED

                # TODO: DB에 작업 완료 기록
                #   - transport_tasks.task_status → 'COMPLETED'
                #   - transport_tasks.completed_at → NOW()
                #   - 출고 완료 시 farm_nodes 상태 초기화 (SR-38)

            self.current_task = None
            self.status = AgvStatus.IDLE

        elif result == "FAIL":
            print(f"❌ [AgvManager] AGV {agv_id} Task 실패!")
            if self.current_task:
                self.current_task.status = TaskStatus.FAILED

                # TODO: 재시도 로직
                #   - SR-20: 작업 실패 시 작업 중지 + 사용자 앱 경고 알림
                #   - 최대 재시도 횟수 초과 시 에러 로깅 후 스킵
                print(f"🔄 [AgvManager] Task [{self.current_task.task_id}] "
                      f"재시도 여부 판단 필요")

            self.current_task = None
            self.status = AgvStatus.IDLE

    # ──────────── AGV에 명령 전송 (내부 메서드) ────────────
    def _send_command_to_agv(self, task: TransportTask):
        """
        AGV 펌웨어(ESP32)에 이동/작업 명령을 전송한다. (뼈대)

        실제 구현 시:
            1. TransportTask를 JSON 패킷으로 직렬화
            2. TCP 소켓을 통해 ESP32에 전송
            3. ACK 응답 대기
        """
        # TODO: 실제 통신 로직 구현
        print(f"📡 [AgvManager] AGV에 명령 전송 중... "
              f"({task.source_node} → {task.destination_node})")
        pass

    # ──────────── 현재 상태 요약 ────────────
    def get_status_summary(self) -> dict:
        """AGV의 현재 상태를 딕셔너리로 반환한다 (GUI 대시보드 연동용)."""
        return {
            "agv_id": self.agv_id,
            "position": {"x": self.pos_x, "y": self.pos_y},
            "battery": self.battery_level,
            "status": self.status.value,
            "current_task": self.current_task.task_id if self.current_task else None,
            "queue_size": self.task_queue.size,
        }
