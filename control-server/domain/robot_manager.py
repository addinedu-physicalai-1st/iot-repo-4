"""
robot_manager.py
================
무인 이송 로봇의 상태(위치, 배터리, 동작 상태)를 추적하고,
RobotTaskQueue를 통해 Task를 할당·관리하는 매니저 모듈.
"""

from enum import Enum
from domain.robot_task import RobotTaskQueue, RobotTask, TaskStatus


class RobotState(Enum):
    """로봇의 현재 동작 상태"""
    IDLE = "idle"              # 대기 중
    MOVING = "moving"          # 이동 중
    WORKING = "working"        # 작업 수행 중 (Pick-and-Place 등)
    CHARGING = "charging"      # 충전 중
    ERROR = "error"            # 오류 상태


class RobotManager:
    """
    로봇의 실시간 상태를 관리하고, Task를 할당하는 매니저 클래스.

    추적 정보:
        - 현재 위치 (X, Y)
        - 배터리 잔량 (%)
        - 동작 상태 (RobotState)
        - 현재 수행 중인 Task

    의존성:
        - RobotTaskQueue : 작업 큐에서 Task를 가져와 할당
    """

    # 배터리가 이 값 이하이면 충전이 필요하다고 판단
    LOW_BATTERY_THRESHOLD = 20  # (%)

    def __init__(self, task_queue: RobotTaskQueue):
        """
        Args:
            task_queue : RobotTaskQueue 인스턴스 (DI – 의존성 주입)
        """
        self.task_queue = task_queue

        # ── 로봇 상태 초기화 ──
        self.position_x: float = 0.0        # 현재 X 좌표
        self.position_y: float = 0.0        # 현재 Y 좌표
        self.battery: float = 100.0         # 배터리 잔량 (%)
        self.state: RobotState = RobotState.IDLE
        self.current_task: RobotTask | None = None  # 현재 수행 중인 Task

    # ──────────── 로봇 상태 업데이트 ────────────
    def update_robot_status(self, robot_id: int, payload: dict):
        """
        네트워크에서 수신된 로봇 상태 정보를 반영한다.

        Args:
            robot_id : 로봇 식별 ID
            payload  : 상태 정보 딕셔너리
                       예: {"x": 150.0, "y": 200.0, "battery": 85, "state": "idle"}
        """
        # 위치 정보 갱신
        if "x" in payload:
            self.position_x = payload["x"]
        if "y" in payload:
            self.position_y = payload["y"]

        # 배터리 정보 갱신
        if "battery" in payload:
            self.battery = payload["battery"]
            # 배터리 부족 경고
            if self.battery <= self.LOW_BATTERY_THRESHOLD:
                print(f"🪫 [RobotManager] ⚠️ 로봇 {robot_id} 배터리 부족! "
                      f"({self.battery}%) → 충전 필요")

        # 상태 정보 갱신
        if "state" in payload:
            try:
                self.state = RobotState(payload["state"])
            except ValueError:
                print(f"⚠️ [RobotManager] 알 수 없는 상태값: {payload['state']}")

        print(f"🤖 [RobotManager] 로봇 {robot_id} 상태 갱신 → "
              f"위치=({self.position_x}, {self.position_y}), "
              f"배터리={self.battery}%, 상태={self.state.value}")

    # ──────────── Task 할당 ────────────
    def assign_next_task(self) -> RobotTask | None:
        """
        큐에서 다음 Task를 꺼내 로봇에게 할당한다.

        Returns:
            할당된 RobotTask 또는 None (큐가 비어있거나 로봇이 작업 중일 때)
        """
        # 로봇이 이미 작업 중이면 새 Task 할당 불가
        if self.state != RobotState.IDLE:
            print(f"⚠️ [RobotManager] 로봇이 현재 '{self.state.value}' 상태입니다. "
                  f"IDLE 상태에서만 Task 할당 가능.")
            return None

        # 배터리 부족 시 Task 할당 거부
        if self.battery <= self.LOW_BATTERY_THRESHOLD:
            print(f"🪫 [RobotManager] 배터리 부족({self.battery}%)으로 Task 할당 불가. "
                  f"충전이 필요합니다.")
            return None

        # 큐에서 다음 Task 가져오기
        task = self.task_queue.get_next_task()
        if task:
            self.current_task = task
            self.state = RobotState.WORKING
            print(f"✅ [RobotManager] Task [{task.task_id}] 할당 완료 → "
                  f"'{task.description}'")

            # TODO: 실제로 로봇 펌웨어에 Task 명령을 전송하는 로직
            # - 시리얼 통신 또는 Wi-Fi를 통해 ESP32에 명령 패킷 전송
            # - 명령 포맷: JSON 또는 바이너리 프로토콜
            self._send_task_to_robot(task)
        else:
            print("ℹ️  [RobotManager] 할당할 Task가 없습니다.")

        return task

    # ──────────── 작업 결과 처리 ────────────
    def handle_task_result(self, robot_id: int, result: str):
        """
        로봇에서 수신한 작업 완료/실패 결과를 처리한다.

        Args:
            robot_id : 로봇 식별 ID
            result   : "success" 또는 "fail"
        """
        if result == "success":
            print(f"🎉 [RobotManager] 로봇 {robot_id} Task 성공!")
            if self.current_task:
                self.current_task.status = TaskStatus.COMPLETED
            self.current_task = None
            self.state = RobotState.IDLE

            # TODO: DB에 작업 완료 로그 기록
            # TODO: 자동으로 다음 Task 할당 여부 판단

        elif result == "fail":
            print(f"❌ [RobotManager] 로봇 {robot_id} Task 실패!")
            if self.current_task:
                self.current_task.status = TaskStatus.FAILED
                # TODO: 재시도 로직 – 실패한 Task를 큐 앞쪽에 다시 넣을지 판단
                #       최대 재시도 횟수를 초과하면 에러 로깅 후 스킵
                print(f"🔄 [RobotManager] Task [{self.current_task.task_id}] "
                      f"재시도 여부 판단 필요")
            self.current_task = None
            self.state = RobotState.IDLE

    # ──────────── 로봇에 Task 전송 (내부 메서드) ────────────
    def _send_task_to_robot(self, task: RobotTask):
        """
        로봇 펌웨어(ESP32)에 Task 명령을 전송한다. (뼈대)

        실제 구현 시:
            1. Task 객체를 JSON 패킷으로 직렬화
            2. Wi-Fi TCP/UDP 또는 시리얼 통신으로 ESP32에 전송
            3. 전송 확인(ACK) 대기
        """
        # TODO: 실제 통신 로직 구현
        print(f"📡 [RobotManager] 로봇에 Task 전송 중... "
              f"(target=({task.target_x}, {task.target_y}))")
        pass

    # ──────────── 현재 상태 요약 ────────────
    def get_status_summary(self) -> dict:
        """로봇의 현재 상태를 딕셔너리로 반환한다 (GUI 대시보드 연동용)."""
        return {
            "position": {"x": self.position_x, "y": self.position_y},
            "battery": self.battery,
            "state": self.state.value,
            "current_task": self.current_task.task_id if self.current_task else None,
            "queue_size": self.task_queue.size,
        }
