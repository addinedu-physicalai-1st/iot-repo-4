"""
robot_task.py
=============
로봇이 수행할 작업(Task)을 정의하고, 작업 큐를 관리하는 모듈.

핵심 미션:
    so-arm(STS3215 모터 기반)을 이용해 물고기 인형을 집어
    바구니에 5회 옮겨 담는 Pick-and-Place 작업
"""

from enum import Enum
from dataclasses import dataclass, field
from collections import deque
from datetime import datetime


# ──────────────────────────────────────────────
#  열거형: Task 상태 및 타입 정의
# ──────────────────────────────────────────────

class TaskStatus(Enum):
    """작업의 현재 진행 상태"""
    PENDING = "pending"        # 대기 중 (큐에 등록됨)
    IN_PROGRESS = "in_progress"  # 실행 중
    COMPLETED = "completed"    # 완료
    FAILED = "failed"          # 실패


class TaskType(Enum):
    """작업 종류"""
    PICK_AND_PLACE = "pick_and_place"  # 물고기 인형 Pick-and-Place
    TRANSPORT = "transport"            # 작물 이송
    RETURN_HOME = "return_home"        # 홈 위치 복귀
    CHARGE = "charge"                  # 충전 스테이션 이동


# ──────────────────────────────────────────────
#  데이터 클래스: 단위 Task 객체 정의
# ──────────────────────────────────────────────

@dataclass
class RobotTask:
    """
    로봇이 수행할 단위 작업 객체.

    Attributes:
        task_id      : 고유 작업 ID
        task_type    : 작업 종류 (TaskType 열거형)
        description  : 작업 설명 (사람이 읽을 수 있는 텍스트)
        target_x     : 목표 X 좌표
        target_y     : 목표 Y 좌표
        repeat_count : 반복 횟수 (Pick-and-Place의 경우 기본 5회)
        status       : 현재 작업 상태
        created_at   : 작업 생성 시각
        params       : 추가 파라미터 (작업별 커스텀 설정)
    """
    task_id: int
    task_type: TaskType
    description: str = ""
    target_x: float = 0.0
    target_y: float = 0.0
    repeat_count: int = 1
    status: TaskStatus = TaskStatus.PENDING
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    params: dict = field(default_factory=dict)


# ──────────────────────────────────────────────
#  로봇 작업 큐 클래스
# ──────────────────────────────────────────────

class RobotTaskQueue:
    """
    로봇이 수행할 Task 목록을 FIFO 큐 형태로 관리하는 클래스.

    주요 기능:
        - Task 추가 / 꺼내기 / 조회
        - Pick-and-Place 미션 전용 Task 생성 헬퍼
        - 큐 상태 확인
    """

    def __init__(self):
        """큐 초기화. 내부적으로 deque를 사용한다."""
        self._queue: deque[RobotTask] = deque()
        self._task_id_counter: int = 0  # 자동 증가 ID

    # ──────────── Task ID 자동 생성 ────────────
    def _next_id(self) -> int:
        """고유한 Task ID를 자동 생성하여 반환한다."""
        self._task_id_counter += 1
        return self._task_id_counter

    # ──────────── Task 추가 ────────────
    def add_task(self, task: RobotTask):
        """
        작업 큐에 새로운 Task를 추가한다.

        Args:
            task : RobotTask 객체
        """
        self._queue.append(task)
        print(f"📥 [TaskQueue] Task 추가: [{task.task_id}] {task.task_type.value} "
              f"- {task.description}")

    # ──────────── 다음 Task 꺼내기 ────────────
    def get_next_task(self) -> RobotTask | None:
        """
        큐에서 다음 대기 중인 Task를 꺼낸다 (FIFO).

        Returns:
            다음 RobotTask 또는 큐가 비었으면 None
        """
        if self._queue:
            task = self._queue.popleft()
            task.status = TaskStatus.IN_PROGRESS
            print(f"📤 [TaskQueue] Task 할당: [{task.task_id}] {task.task_type.value}")
            return task
        else:
            print("ℹ️  [TaskQueue] 큐에 대기 중인 Task가 없습니다.")
            return None

    # ──────────── 큐 상태 확인 ────────────
    def peek(self) -> RobotTask | None:
        """큐의 맨 앞 Task를 꺼내지 않고 확인만 한다."""
        return self._queue[0] if self._queue else None

    @property
    def size(self) -> int:
        """현재 큐에 남아있는 Task 수를 반환한다."""
        return len(self._queue)

    @property
    def is_empty(self) -> bool:
        """큐가 비었는지 확인한다."""
        return len(self._queue) == 0

    def get_all_tasks(self) -> list[RobotTask]:
        """현재 큐에 들어있는 전체 Task 리스트를 반환한다 (큐에서 제거하지 않음)."""
        return list(self._queue)

    # ──────────────────────────────────────────────
    #  🐟 Pick-and-Place 미션 전용 Task 생성 헬퍼
    # ──────────────────────────────────────────────
    def create_pick_and_place_task(
        self,
        pick_x: float,
        pick_y: float,
        place_x: float,
        place_y: float,
        repeat: int = 5,
    ) -> RobotTask:
        """
        대회 핵심 미션인 '물고기 인형 Pick-and-Place' Task를 생성하고 큐에 추가한다.

        미션 상세:
            - so-arm(STS3215 서보 모터 기반) 로봇 암을 사용
            - 지정된 pick 좌표에서 물고기 인형을 그리퍼로 집음
            - 지정된 place 좌표(바구니)까지 이동하여 놓음
            - 위 동작을 repeat 횟수만큼 반복 (기본 5회)

        Args:
            pick_x  : 물고기 인형 위치 X 좌표
            pick_y  : 물고기 인형 위치 Y 좌표
            place_x : 바구니(목적지) 위치 X 좌표
            place_y : 바구니(목적지) 위치 Y 좌표
            repeat  : 반복 횟수 (기본값: 5)

        Returns:
            생성된 RobotTask 객체
        """
        task = RobotTask(
            task_id=self._next_id(),
            task_type=TaskType.PICK_AND_PLACE,
            description=f"🐟 물고기 인형 Pick-and-Place ({repeat}회 반복)",
            target_x=place_x,
            target_y=place_y,
            repeat_count=repeat,
            params={
                # ── so-arm 관련 파라미터 ──
                "pick_position": {"x": pick_x, "y": pick_y},
                "place_position": {"x": place_x, "y": place_y},
                "arm_type": "so-arm",                # 사용할 로봇 암 종류
                "motor_model": "STS3215",             # 서보 모터 모델명
                "gripper_open_angle": 90,             # 그리퍼 열림 각도 (도)
                "gripper_close_angle": 30,            # 그리퍼 닫힘 각도 (물체 파지)
                "lift_height": 50,                    # 물체를 들어올릴 높이 (mm)
                "approach_speed": 100,                # 접근 속도 (mm/s)
                "retreat_speed": 80,                  # 후퇴 속도 (mm/s)
            },
        )

        self.add_task(task)
        print(f"🎯 [TaskQueue] Pick-and-Place 미션 등록 완료 "
              f"(pick→({pick_x},{pick_y}), place→({place_x},{place_y}), {repeat}회)")

        return task
