"""
system_controller.py
====================
통합 스마트팜 자동화 시스템의 최상위 컨트롤러.
모든 매니저/라우터를 인스턴스화하고 하나로 묶어
시스템의 전체 흐름을 관장한다.

SA 대응:
    이 클래스 = SA 다이어그램의 'SFAM_Service' (중앙서버 핵심)

의존성 그래프:
    DatabaseManager
    ├─ FarmRepository ─────────┬─ SearchDeviceManager
    ├─ AgvRepository           ├─ NurseryControllerManager
    └─ NurseryRepository ──────┘
    TransportTaskQueue ─── AgvManager
                  ↕
    모두 → MessageRouter → SystemController
"""

from database.db_manager import DatabaseManager
from database.farm_repository import FarmRepository
from database.agv_repository import AgvRepository
from database.nursery_repository import NurseryRepository
from domain.transport_task import TransportTaskQueue
from domain.agv_manager import AgvManager
from domain.farm_env_manager import FarmEnvManager
from domain.search_device_manager import SearchDeviceManager
from domain.nursery_controller_manager import NurseryControllerManager
from network.message_router import MessageRouter


class SystemController:
    """
    시스템 전체를 지휘하는 최상위 컨트롤러 클래스.

    역할:
        1. 모든 하위 컴포넌트를 올바른 순서로 초기화 (DI)
        2. DB 연결 관리 (시작/종료)
        3. 외부에서 수신된 패킷을 MessageRouter에 전달
        4. 시스템 상태 요약 정보 제공 (GUI 대시보드 연동)
    """

    def __init__(self):
        """
        모든 컴포넌트를 생성하고 의존성을 주입(DI)한다.
        아직 DB 연결은 하지 않은 상태 – start()에서 연결한다.
        """
        # ── 1) 데이터베이스 계층 ──
        self.db_manager = DatabaseManager()
        self.farm_repo = FarmRepository(self.db_manager)
        self.agv_repo = AgvRepository(self.db_manager)
        self.nursery_repo = NurseryRepository(self.db_manager)

        # ── 2) 도메인 계층 ──
        self.task_queue = TransportTaskQueue()
        self.agv_manager = AgvManager(self.task_queue)
        self.farm_env_manager = FarmEnvManager(self.farm_repo)  # 하위호환 유지
        self.search_device_manager = SearchDeviceManager(self.farm_repo, self.task_queue)
        self.nursery_ctrl_manager = NurseryControllerManager(
            self.nursery_repo, self.farm_repo
        )

        # ── 3) 네트워크 계층 ──
        self.message_router = MessageRouter(
            agv_manager=self.agv_manager,
            nursery_ctrl_manager=self.nursery_ctrl_manager,
            search_device_manager=self.search_device_manager,
            task_queue=self.task_queue,
        )

        print("🏗️ [SystemController] 모든 컴포넌트 초기화 완료")

    # ──────────── 시스템 시작 ────────────
    def start(self):
        """
        시스템을 시작한다.

        순서:
            1. DB 연결
            2. 초기 데이터 로드 (노드 목록, AGV 목록 등)
            3. 네트워크 서버 리스닝 시작 (추후 구현)
        """
        print()
        print("🌱 ======================================== 🌱")
        print("   통합 스마트팜 자동화 시스템 – 시작")
        print("🌱 ======================================== 🌱")
        print()

        # 1) DB 연결
        self.db_manager.connect()
        if not self.db_manager.connection:
            print("🚫 [SystemController] DB 연결 실패 → 시스템 시작 중단")
            return False

        # 2) 초기 데이터 로드
        self._load_initial_data()

        # 3) TODO: TCP/UDP 소켓 서버 시작
        print("\n🟢 [SystemController] 시스템이 정상적으로 시작되었습니다.")
        return True

    # ──────────── 시스템 종료 ────────────
    def stop(self):
        """시스템을 안전하게 종료한다."""
        print("\n🔴 [SystemController] 시스템 종료 중...")
        # TODO: 네트워크 서버 종료, 실행 중인 Task 정리
        self.db_manager.disconnect()
        print("🏁 [SystemController] 시스템이 안전하게 종료되었습니다.\n")

    # ──────────── 초기 데이터 로드 ────────────
    def _load_initial_data(self):
        """시스템 시작 시 DB에서 필요한 초기 데이터를 로드한다."""
        print("\n📥 [SystemController] 초기 데이터 로드 중...")

        # 팜 노드 목록
        nodes = self.farm_repo.get_all_nodes()
        if nodes:
            print(f"   📋 팜 노드 {len(nodes)}개 로드 완료")

        # 빈 슬롯 확인
        empty_slots = self.farm_repo.find_empty_slots()
        print(f"   🔍 빈 슬롯 {len(empty_slots)}개 확인")

        # AGV 목록
        agvs = self.agv_repo.get_all_agvs()
        print(f"   🤖 AGV {len(agvs)}대 로드 완료")

        # 온라인 제어기 목록
        controllers = self.nursery_repo.get_all_online_controllers()
        print(f"   🌡️ 온라인 제어기 {len(controllers)}대 확인")

    # ──────────── 패킷 수신 처리 ────────────
    def handle_udp_data(self, raw_data: str):
        """외부 UDP 데이터를 MessageRouter에 전달한다."""
        self.message_router.route_udp(raw_data)

    def handle_tcp_data(self, raw_data: str) -> dict:
        """외부 TCP 데이터를 MessageRouter에 전달하고 응답을 반환한다."""
        return self.message_router.route_tcp(raw_data)

    # ──────────── 시스템 상태 요약 ────────────
    def get_system_status(self) -> dict:
        """전체 시스템 상태를 딕셔너리로 반환한다 (GUI 대시보드 연동)."""
        return {
            "db_connected": (
                self.db_manager.connection is not None
                and self.db_manager.connection.open
            ),
            "agv": self.agv_manager.get_status_summary(),
            "nursery_controllers": self.nursery_ctrl_manager.get_all_controller_status(),
            "task_queue_size": self.task_queue.size,
        }

    # ──────────── 컨텍스트 매니저 지원 ────────────
    def __enter__(self):
        """with 문 진입 시 시스템을 시작한다."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """with 문 종료 시 시스템을 안전하게 종료한다."""
        self.stop()
