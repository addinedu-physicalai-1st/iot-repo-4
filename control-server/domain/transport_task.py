"""
transport_task.py
=================
운송 작업(Transport Task)을 정의하고, 작업 큐를 관리하는 모듈.
DB 스키마의 transport_tasks 테이블과 연동된다.

참조 스키마: docs/DB_SCHEMA.md § 3. 무인 운반차 (AGV)
  - transport_tasks.task_id         : INT – PK
  - transport_tasks.task_status     : ENUM ('PENDING','IN_PROGRESS','COMPLETED','FAILED')
  - transport_tasks.source_node     : VARCHAR(50) – FK → farm_nodes
  - transport_tasks.destination_node: VARCHAR(50) – FK → farm_nodes

SR 참조:
  - SR-39: 진행 중 명령 우선 처리
  - SR-40: 출고 명령 > 입고 명령 우선순위
  - SR-41: 유휴 상태 배회 감시
"""

from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
import heapq


# ──────────────────────────────────────────────
#  열거형: 작업 상태 및 종류 정의
# ──────────────────────────────────────────────

class TaskStatus(Enum):
    """운송 작업의 현재 진행 상태 (DB ENUM과 일치)"""
    PENDING = "PENDING"            # 대기 중 (큐에 등록됨)
    IN_PROGRESS = "IN_PROGRESS"    # 실행 중
    COMPLETED = "COMPLETED"        # 완료
    FAILED = "FAILED"              # 실패


class TaskType(Enum):
    """
    작업 종류.
    우선순위 값이 낮을수록 먼저 처리된다.
    (SR-40: 출고 > 입고)
    """
    OUTBOUND = ("OUTBOUND", 1)    # 출고 – 최우선
    INBOUND = ("INBOUND", 2)      # 입고
    MANUAL = ("MANUAL", 3)        # 수동 이동

    def __init__(self, label: str, priority: int):
        self.label = label
        self._priority = priority

    @property
    def priority(self) -> int:
        return self._priority


# ──────────────────────────────────────────────
#  데이터 클래스: 운송 작업 객체 (transport_tasks 테이블 매핑)
# ──────────────────────────────────────────────

@dataclass(order=False)
class TransportTask:
    """
    운송 작업 단위 객체. DB의 transport_tasks 행 1개에 대응한다.

    Attributes:
        task_id          : 작업 고유 ID (DB PK, 0이면 아직 미저장)
        task_type        : 작업 종류 (OUTBOUND / INBOUND / MANUAL)
        agv_id           : 할당된 AGV ID (VARCHAR(20))
        variety_id       : 운반 품종 ID
        source_node      : 출발지 노드 ID (VARCHAR(50))
        destination_node : 목적지 노드 ID (VARCHAR(50))
        ordered_by       : 지시자 사용자 ID
        quantity         : 운반 수량
        status           : 현재 작업 상태
        ordered_at       : 작업 지시 시각
    """
    task_id: int = 0
    task_type: TaskType = TaskType.INBOUND
    agv_id: str = ""
    variety_id: int | None = None
    source_node: str = ""
    destination_node: str = ""
    ordered_by: int | None = None
    quantity: int = 1
    status: TaskStatus = TaskStatus.PENDING
    ordered_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def __lt__(self, other: "TransportTask") -> bool:
        """우선순위 비교: priority 값이 작을수록 먼저 처리된다."""
        return self.task_type.priority < other.task_type.priority


# ──────────────────────────────────────────────
#  운송 작업 큐 (우선순위 큐)
# ──────────────────────────────────────────────

class TransportTaskQueue:
    """
    운송 작업을 우선순위 기반으로 관리하는 큐 클래스.

    우선순위 규칙 (SR-40):
        1) 출고(OUTBOUND) – 가장 높은 우선순위
        2) 입고(INBOUND)
        3) 수동(MANUAL)

    내부적으로 Python heapq(최소 힙)를 사용한다.
    """

    def __init__(self):
        """큐 초기화."""
        self._heap: list[TransportTask] = []
        self._task_id_counter: int = 0

    # ──────────── Task ID 자동 생성 ────────────
    def _next_id(self) -> int:
        """고유한 Task ID를 자동 생성하여 반환한다."""
        self._task_id_counter += 1
        return self._task_id_counter

    # ──────────── Task 추가 ────────────
    def add_task(self, task: TransportTask):
        """
        큐에 새로운 운송 작업을 추가한다.
        우선순위에 따라 자동으로 정렬된다.

        Args:
            task : TransportTask 객체
        """
        if task.task_id == 0:
            task.task_id = self._next_id()

        heapq.heappush(self._heap, task)
        print(f"📥 [TaskQueue] Task 추가: [{task.task_id}] {task.task_type.label} "
              f"({task.source_node} → {task.destination_node})")

    # ──────────── 다음 Task 꺼내기 ────────────
    def get_next_task(self) -> TransportTask | None:
        """
        큐에서 가장 우선순위가 높은 Task를 꺼낸다.

        Returns:
            다음 TransportTask 또는 큐가 비었으면 None
        """
        if self._heap:
            task = heapq.heappop(self._heap)
            task.status = TaskStatus.IN_PROGRESS
            print(f"📤 [TaskQueue] Task 할당: [{task.task_id}] {task.task_type.label} "
                  f"(우선순위: {task.task_type.priority})")
            return task
        else:
            print("ℹ️  [TaskQueue] 큐에 대기 중인 Task가 없습니다.")
            return None

    # ──────────── 큐 상태 확인 ────────────
    @property
    def size(self) -> int:
        """현재 큐에 남아있는 Task 수를 반환한다."""
        return len(self._heap)

    @property
    def is_empty(self) -> bool:
        """큐가 비었는지 확인한다."""
        return len(self._heap) == 0

    def get_all_tasks(self) -> list[TransportTask]:
        """현재 큐에 들어있는 전체 Task 리스트를 반환한다 (정렬된 사본)."""
        return sorted(self._heap)

    # ──────────── 편의 메서드: 입고 Task 생성 ────────────
    def create_inbound_task(
        self,
        source_node: str,
        destination_node: str,
        variety_id: int,
        quantity: int = 1,
    ) -> TransportTask:
        """
        입고 운송 작업을 생성하고 큐에 추가한다.
        (SR-13~18: 입고장 → 육묘 섹션 저장고)

        Args:
            source_node      : 출발지 (입고장 노드 ID)
            destination_node : 목적지 (육묘 저장고 노드 ID)
            variety_id       : 운반 품종 ID
            quantity         : 운반 수량
        """
        task = TransportTask(
            task_type=TaskType.INBOUND,
            source_node=source_node,
            destination_node=destination_node,
            variety_id=variety_id,
            quantity=quantity,
        )
        self.add_task(task)
        return task

    # ──────────── 편의 메서드: 출고 Task 생성 ────────────
    def create_outbound_task(
        self,
        source_node: str,
        destination_node: str,
        variety_id: int,
        quantity: int = 1,
    ) -> TransportTask:
        """
        출고 운송 작업을 생성하고 큐에 추가한다.
        (SR-34~37: 육묘 저장고 → 출고장)

        Args:
            source_node      : 출발지 (육묘 저장고 노드 ID)
            destination_node : 목적지 (출고장 노드 ID)
            variety_id       : 운반 품종 ID
            quantity         : 운반 수량
        """
        task = TransportTask(
            task_type=TaskType.OUTBOUND,
            source_node=source_node,
            destination_node=destination_node,
            variety_id=variety_id,
            quantity=quantity,
        )
        self.add_task(task)
        return task
