"""
system_controller.py
====================
통합 스마트팜 자동화 시스템의 최상위 컨트롤러.
모든 매니저/라우터를 인스턴스화하고 하나로 묶어
시스템의 전체 흐름을 관장한다.
"""

from database.db_manager import DatabaseManager
from database.farm_repository import FarmRepository
from network.packet_router import PacketRouter
from domain.robot_task import RobotTaskQueue
from domain.robot_manager import RobotManager
from domain.farm_env_manager import FarmEnvManager


class SystemController:
    """
    시스템 전체를 지휘하는 최상위 컨트롤러 클래스.

    구성 요소 (의존성 그래프):
        DatabaseManager
            └─ FarmRepository
                 └─ FarmEnvManager ─┐
        RobotTaskQueue              ├─ PacketRouter
            └─ RobotManager ────────┘

    역할:
        1. 모든 하위 컴포넌트를 올바른 순서로 초기화
        2. DB 연결 관리 (시작/종료)
        3. 외부에서 수신된 패킷을 PacketRouter에 전달
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

        # ── 2) 도메인 계층 ──
        self.task_queue = RobotTaskQueue()
        self.robot_manager = RobotManager(self.task_queue)
        self.farm_env_manager = FarmEnvManager(self.farm_repo)

        # ── 3) 네트워크 계층 ──
        self.packet_router = PacketRouter(
            farm_env_manager=self.farm_env_manager,
            robot_manager=self.robot_manager,
        )

        print("🏗️ [SystemController] 모든 컴포넌트 초기화 완료")

    # ──────────── 시스템 시작 ────────────
    def start(self):
        """
        시스템을 시작한다.

        순서:
            1. DB 연결
            2. 초기 데이터 로드 (노드 목록 등)
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

        # 3) TODO: TCP/UDP 소켓 서버 시작하여 ESP32 디바이스 연결 대기
        #    예: asyncio 기반 서버 또는 threading 기반 서버
        print("\n🟢 [SystemController] 시스템이 정상적으로 시작되었습니다.")
        return True

    # ──────────── 시스템 종료 ────────────
    def stop(self):
        """
        시스템을 안전하게 종료한다.

        순서:
            1. 네트워크 서버 종료 (추후 구현)
            2. DB 연결 해제
        """
        print("\n🔴 [SystemController] 시스템 종료 중...")

        # TODO: 네트워크 서버 종료 처리
        # TODO: 실행 중인 로봇 Task 안전하게 중단

        self.db_manager.disconnect()
        print("🏁 [SystemController] 시스템이 안전하게 종료되었습니다.\n")

    # ──────────── 초기 데이터 로드 ────────────
    def _load_initial_data(self):
        """
        시스템 시작 시 DB에서 필요한 초기 데이터를 로드한다.
        """
        print("\n📥 [SystemController] 초기 데이터 로드 중...")

        # 전체 노드 목록 가져오기
        nodes = self.farm_repo.get_all_nodes()
        if nodes:
            print(f"   📋 팜 노드 {len(nodes)}개 로드 완료")
        else:
            print("   ⚠️ 팜 노드 데이터 로드 실패 또는 데이터 없음")

        # 빈 슬롯 확인
        empty_slots = self.farm_repo.find_empty_slots()
        print(f"   🔍 빈 슬롯 {len(empty_slots)}개 확인")

    # ──────────── 패킷 수신 처리 ────────────
    def handle_incoming_data(self, raw_data: str):
        """
        외부(네트워크)에서 수신된 원시 데이터를 PacketRouter에 전달한다.

        Args:
            raw_data : JSON 형식의 원시 문자열
        """
        self.packet_router.route(raw_data)

    # ──────────── 시스템 상태 요약 ────────────
    def get_system_status(self) -> dict:
        """
        전체 시스템 상태를 딕셔너리로 반환한다.
        GUI 대시보드에서 실시간 모니터링에 활용.

        Returns:
            시스템 상태 요약 딕셔너리
        """
        return {
            "db_connected": (
                self.db_manager.connection is not None
                and self.db_manager.connection.open
            ),
            "robot": self.robot_manager.get_status_summary(),
            "environments": self.farm_env_manager.get_all_environments(),
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
