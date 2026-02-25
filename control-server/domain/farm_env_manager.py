"""
farm_env_manager.py
===================
육묘장 환경(온도, 습도)을 모니터링하고,
목표 범위를 벗어났을 때 제어 조치를 판단하는 비즈니스 로직 모듈.
"""

from database.farm_repository import FarmRepository


class FarmEnvManager:
    """
    육묘 환경 제어 매니저.

    역할:
        - 각 노드의 온/습도 데이터를 수신하여 모니터링
        - 목표 온습도 범위를 벗어나면 쿨링 팬 / 히터 / 가습기 등 제어 명령 생성
        - 환경 데이터를 DB에 기록 (FarmRepository 활용)

    의존성:
        - FarmRepository : DB에 환경 데이터 기록 및 노드 상태 업데이트
    """

    # ──────────────────────────────────────────────
    #  목표 환경 설정값 (기본값 – 추후 DB 또는 GUI에서 변경 가능)
    # ──────────────────────────────────────────────
    DEFAULT_TARGET_TEMP_MIN = 20.0   # 최소 목표 온도 (°C)
    DEFAULT_TARGET_TEMP_MAX = 28.0   # 최대 목표 온도 (°C)
    DEFAULT_TARGET_HUM_MIN = 50.0    # 최소 목표 습도 (%)
    DEFAULT_TARGET_HUM_MAX = 70.0    # 최대 목표 습도 (%)

    def __init__(self, farm_repository: FarmRepository):
        """
        Args:
            farm_repository : FarmRepository 인스턴스 (DI – 의존성 주입)
        """
        self.repo = farm_repository

        # ── 목표 환경 범위 설정 ──
        self.target_temp_min = self.DEFAULT_TARGET_TEMP_MIN
        self.target_temp_max = self.DEFAULT_TARGET_TEMP_MAX
        self.target_hum_min = self.DEFAULT_TARGET_HUM_MIN
        self.target_hum_max = self.DEFAULT_TARGET_HUM_MAX

        # ── 최근 수신된 각 노드의 환경 데이터 캐시 ──
        # { node_id: {"temperature": float, "humidity": float} }
        self._env_cache: dict[int, dict] = {}

    # ──────────── 환경 데이터 업데이트 (메인 진입점) ────────────
    def update_environment(self, node_id: int, temperature: float, humidity: float):
        """
        센서에서 수신된 환경 데이터를 처리한다.

        처리 흐름:
            1) 캐시에 최신 데이터 저장
            2) DB에 현재 환경 데이터 업데이트
            3) DB에 센서 로그 기록
            4) 온도/습도가 목표 범위를 벗어났는지 판단
            5) 범위 초과 시 제어 조치 실행

        Args:
            node_id     : 센서가 설치된 노드 ID
            temperature : 측정 온도 (°C)
            humidity    : 측정 습도 (%)
        """
        print(f"\n🌡️ [FarmEnvManager] 노드 {node_id} 환경 수신: "
              f"온도={temperature}°C, 습도={humidity}%")

        # 1) 캐시 업데이트
        self._env_cache[node_id] = {
            "temperature": temperature,
            "humidity": humidity,
        }

        # 2) DB에 현재 환경 데이터 반영
        self.repo.update_node_environment(node_id, temperature, humidity)

        # 3) 센서 로그 기록
        self.repo.insert_sensor_log(node_id, temperature, humidity)

        # 4) 환경 이상 여부 판단 및 제어 조치
        self._check_and_control(node_id, temperature, humidity)

    # ──────────── 목표 범위 설정 변경 ────────────
    def set_target_range(
        self,
        temp_min: float = None,
        temp_max: float = None,
        hum_min: float = None,
        hum_max: float = None,
    ):
        """
        목표 온습도 범위를 변경한다. (GUI 대시보드에서 호출)

        Args:
            temp_min : 최소 목표 온도 (None이면 변경 안 함)
            temp_max : 최대 목표 온도
            hum_min  : 최소 목표 습도
            hum_max  : 최대 목표 습도
        """
        if temp_min is not None:
            self.target_temp_min = temp_min
        if temp_max is not None:
            self.target_temp_max = temp_max
        if hum_min is not None:
            self.target_hum_min = hum_min
        if hum_max is not None:
            self.target_hum_max = hum_max

        print(f"⚙️ [FarmEnvManager] 목표 범위 변경: "
              f"온도={self.target_temp_min}~{self.target_temp_max}°C, "
              f"습도={self.target_hum_min}~{self.target_hum_max}%")

    # ──────────── 환경 이상 판단 및 제어 ────────────
    def _check_and_control(self, node_id: int, temperature: float, humidity: float):
        """
        현재 온습도가 목표 범위 내에 있는지 확인하고,
        범위를 벗어나면 적절한 제어 조치를 실행한다.
        """
        # ─── 온도 판단 ───
        if temperature > self.target_temp_max:
            # 온도가 너무 높음 → 쿨링 팬 가동
            print(f"🔴 [FarmEnvManager] 노드 {node_id}: 온도 초과 "
                  f"({temperature}°C > {self.target_temp_max}°C)")
            self._activate_cooling_fan(node_id)

        elif temperature < self.target_temp_min:
            # 온도가 너무 낮음 → 히터 가동
            print(f"🔵 [FarmEnvManager] 노드 {node_id}: 온도 부족 "
                  f"({temperature}°C < {self.target_temp_min}°C)")
            self._activate_heater(node_id)

        else:
            print(f"🟢 [FarmEnvManager] 노드 {node_id}: 온도 정상 범위 ✅")

        # ─── 습도 판단 ───
        if humidity > self.target_hum_max:
            # 습도가 너무 높음 → 환기 팬 가동
            print(f"🔴 [FarmEnvManager] 노드 {node_id}: 습도 초과 "
                  f"({humidity}% > {self.target_hum_max}%)")
            self._activate_ventilation(node_id)

        elif humidity < self.target_hum_min:
            # 습도가 너무 낮음 → 가습기 가동
            print(f"🔵 [FarmEnvManager] 노드 {node_id}: 습도 부족 "
                  f"({humidity}% < {self.target_hum_min}%)")
            self._activate_humidifier(node_id)

        else:
            print(f"🟢 [FarmEnvManager] 노드 {node_id}: 습도 정상 범위 ✅")

    # ──────────────────────────────────────────────
    #  제어 장치 액추에이터 명령 (뼈대)
    #  실제 구현 시 ESP32 펌웨어에 제어 명령을 전송한다.
    # ──────────────────────────────────────────────

    def _activate_cooling_fan(self, node_id: int):
        """
        쿨링 팬 가동 명령.
        실제 구현 시: ESP32에 팬 ON 명령 패킷을 전송해야 한다.
        """
        # TODO: 네트워크를 통해 해당 노드의 ESP32에 쿨링팬 ON 명령 전송
        # 예: {"type": "control", "node_id": node_id, "device": "cooling_fan", "action": "on"}
        print(f"❄️ [FarmEnvManager] 노드 {node_id}: 쿨링 팬 가동 명령 전송")
        pass

    def _activate_heater(self, node_id: int):
        """
        히터 가동 명령.
        실제 구현 시: ESP32에 히터 ON 명령 패킷을 전송해야 한다.
        """
        # TODO: 네트워크를 통해 해당 노드의 ESP32에 히터 ON 명령 전송
        print(f"🔥 [FarmEnvManager] 노드 {node_id}: 히터 가동 명령 전송")
        pass

    def _activate_ventilation(self, node_id: int):
        """
        환기 팬 가동 명령.
        실제 구현 시: ESP32에 환기 팬 ON 명령 패킷을 전송해야 한다.
        """
        # TODO: 네트워크를 통해 해당 노드의 ESP32에 환기팬 ON 명령 전송
        print(f"💨 [FarmEnvManager] 노드 {node_id}: 환기 팬 가동 명령 전송")
        pass

    def _activate_humidifier(self, node_id: int):
        """
        가습기 가동 명령.
        실제 구현 시: ESP32에 가습기 ON 명령 패킷을 전송해야 한다.
        """
        # TODO: 네트워크를 통해 해당 노드의 ESP32에 가습기 ON 명령 전송
        print(f"💧 [FarmEnvManager] 노드 {node_id}: 가습기 가동 명령 전송")
        pass

    # ──────────── 전체 캐시 환경 조회 ────────────
    def get_all_environments(self) -> dict[int, dict]:
        """
        캐시에 저장된 전체 노드의 최신 환경 데이터를 반환한다.
        (GUI 대시보드에서 실시간 모니터링에 활용)

        Returns:
            { node_id: {"temperature": float, "humidity": float}, ... }
        """
        return self._env_cache.copy()
