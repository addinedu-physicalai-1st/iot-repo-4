"""
nursery_controller_manager.py
=============================
육묘장 환경 제어기(Nursery Controller)를 단위로 관리하는 모듈.
SA 다이어그램의 'Nursery Device' 컴포넌트에 대응한다.

역할:
    - 제어기 단위로 센서 데이터를 수신하고, 환경 이상 판단 (SR-25, SR-26)
    - AUTO/MANUAL 모드 전환 (SR-29)
    - 액추에이터(팬, 히터, 조명, 워터펌프) 제어 명령 판단 (SR-26, SR-30)
    - 센서/액추에이터 동작 로그를 DB에 기록
    - 센서 연결 이상 감지 및 알림 (SR-27)

의존성:
    - NurseryRepository : DB에 센서/액추에이터 로그 기록 및 제어기 상태 관리
    - FarmRepository    : 품종별 최적 환경 설정값 조회
"""

from database.nursery_repository import NurseryRepository
from database.farm_repository import FarmRepository


class NurseryControllerManager:
    """
    육묘장 환경을 제어기(nursery_controller) 단위로 관리하는 매니저 클래스.

    기존 FarmEnvManager 대비 개선점:
        - 센서를 sensor_id 기반으로 개별 관리 (DB 스키마 정합)
        - 제어기별 AUTO/MANUAL 모드 독립 관리 (SR-29)
        - 품종별 최적 환경 설정값을 DB에서 동적 로드
    """

    def __init__(self, nursery_repo: NurseryRepository, farm_repo: FarmRepository):
        """
        Args:
            nursery_repo : NurseryRepository 인스턴스 (DI)
            farm_repo    : FarmRepository 인스턴스 (DI – 품종별 환경 설정 조회)
        """
        self.nursery_repo = nursery_repo
        self.farm_repo = farm_repo

        # ── 제어기별 최신 환경 데이터 캐시 ──
        # { controller_id: {"sensors": {sensor_id: value, ...}, "mode": "AUTO"} }
        self._controller_cache: dict[str, dict] = {}

    # ──────────── 센서 데이터 수신 처리 ────────────
    def handle_sensor_data(self, controller_id: str, sensor_id: int, value: float):
        """
        제어기에서 수신된 센서 데이터를 처리한다.

        처리 흐름:
            1) DB에 센서 로그 기록
            2) 캐시에 최신값 저장
            3) AUTO 모드인 경우 환경 이상 판단 → 액추에이터 제어
            4) 비정상 데이터 감지 시 경고 (SR-27)

        Args:
            controller_id : 데이터를 보낸 제어기 ID
            sensor_id     : 센서 고유 ID
            value         : 측정값
        """
        print(f"🌡️ [NurseryCtrl] 센서 데이터: 제어기={controller_id}, "
              f"센서={sensor_id}, 값={value}")

        # 1) DB에 센서 로그 기록
        self.nursery_repo.insert_sensor_log(sensor_id, value)

        # 2) 캐시 업데이트
        if controller_id not in self._controller_cache:
            self._controller_cache[controller_id] = {"sensors": {}, "mode": "AUTO"}
        self._controller_cache[controller_id]["sensors"][sensor_id] = value

        # 3) 비정상 데이터 감지 (SR-27)
        if not self._is_value_in_valid_range(value):
            print(f"⚠️ [NurseryCtrl] 비정상 센서값 감지! 센서={sensor_id}, 값={value}")
            # TODO: 사용자 앱으로 경고 알림 발송

        # 4) AUTO 모드인 경우에만 자동 제어 판단
        mode = self._controller_cache[controller_id].get("mode", "AUTO")
        if mode == "AUTO":
            self._auto_control_check(controller_id)

    # ──────────── AUTO/MANUAL 모드 전환 (SR-29) ────────────
    def set_control_mode(self, controller_id: str, mode: str):
        """
        제어기의 동작 모드를 전환한다.

        Args:
            controller_id : 제어기 ID
            mode          : 'AUTO' 또는 'MANUAL'
        """
        self.nursery_repo.update_controller_mode(controller_id, mode)

        if controller_id in self._controller_cache:
            self._controller_cache[controller_id]["mode"] = mode

        print(f"⚙️ [NurseryCtrl] 제어기 {controller_id} 모드 변경 → {mode}")

    # ──────────── 수동 장치 제어 (SR-30) ────────────
    def manual_actuator_control(self, actuator_id: int, state: str, user_id: int = None):
        """
        수동 모드에서 특정 액추에이터를 ON/OFF 제어한다.

        Args:
            actuator_id : 구동기 ID
            state       : 'ON' 또는 'OFF'
            user_id     : 제어를 실행한 사용자 ID (로그용)

        TODO (팀원 구현):
            1) 해당 actuator_id에 연결된 ESP32에 제어 명령 전송
            2) 제어 완료 확인
        """
        print(f"🔧 [NurseryCtrl] 수동 제어: 액추에이터={actuator_id}, 상태={state}")

        # DB에 액추에이터 동작 로그 기록
        self.nursery_repo.insert_actuator_log(
            actuator_id=actuator_id,
            state_value=state,
            triggered_by="MANUAL",
        )

        # TODO: ESP32에 제어 명령 전송
        pass

    # ──────────── 제어기 하트비트 처리 ────────────
    def handle_heartbeat(self, controller_id: str):
        """
        제어기에서 수신된 하트비트를 처리한다.
        통신 상태를 ONLINE으로 갱신한다.
        """
        self.nursery_repo.update_heartbeat(controller_id)

    # ──────────── 자동 환경 제어 판단 (내부 메서드) ────────────
    def _auto_control_check(self, controller_id: str):
        """
        현재 센서값과 품종별 최적 환경 설정을 비교하여
        자동 제어가 필요한지 판단한다. (SR-26)

        TODO (팀원 구현):
            1) 제어기가 설치된 노드의 품종 정보를 DB에서 조회
            2) 품종의 opt_temp_day, opt_humidity 등과 현재 센서값 비교
            3) 범위를 벗어나면 해당 액추에이터 ON/OFF 명령 생성
            4) 액추에이터 동작 로그 기록 (triggered_by='AUTO_LOGIC')
        """
        # TODO: 품종별 최적 환경 조회 및 비교 로직
        print(f"🤖 [NurseryCtrl] 제어기 {controller_id}: 자동 환경 판단 중...")
        pass

    # ──────────── 센서값 유효 범위 체크 (SR-27) ────────────
    def _is_value_in_valid_range(self, value: float) -> bool:
        """
        센서 측정값이 물리적으로 유효한 범위인지 확인한다.
        (예: 온도 -40~80, 습도 0~100)

        Returns:
            유효하면 True
        """
        # TODO: 센서 타입별로 유효 범위를 다르게 적용
        if value < -40 or value > 200:
            return False
        return True

    # ──────────── 전체 캐시 조회 ────────────
    def get_all_controller_status(self) -> dict:
        """캐시에 저장된 전체 제어기 상태를 반환한다 (GUI 대시보드 연동)."""
        return self._controller_cache.copy()
