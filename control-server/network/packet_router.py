"""
packet_router.py
================
수신된 JSON 패킷을 파싱하고, 데이터 타입에 따라
적절한 매니저(FarmEnvManager, RobotManager 등)에게 라우팅하는 모듈.
"""

import json


class PacketRouter:
    """
    네트워크로 들어오는 JSON 데이터를 파싱한 뒤,
    패킷 타입(type 필드)에 따라 등록된 핸들러로 분배하는 라우터 클래스.

    의존성:
        - FarmEnvManager  : 센서 데이터 패킷 처리
        - RobotManager    : 로봇 상태/응답 패킷 처리
    """

    def __init__(self, farm_env_manager, robot_manager):
        """
        Args:
            farm_env_manager : FarmEnvManager 인스턴스 (센서 데이터 처리 담당)
            robot_manager    : RobotManager 인스턴스 (로봇 응답 처리 담당)
        """
        self.farm_env_manager = farm_env_manager
        self.robot_manager = robot_manager

        # ── 패킷 타입 → 핸들러 매핑 테이블 ──
        # 새로운 패킷 타입이 추가되면 여기에 등록하면 된다.
        self._route_table: dict[str, callable] = {
            "sensor_data":    self._handle_sensor_data,
            "robot_status":   self._handle_robot_status,
            "robot_response": self._handle_robot_response,
        }

    # ──────────── 메인 라우팅 메서드 ────────────
    def route(self, raw_data: str):
        """
        수신된 원시(raw) JSON 문자열을 파싱하고 적절한 핸들러로 전달한다.

        Args:
            raw_data : 네트워크에서 수신된 JSON 문자열

        패킷 포맷 예시:
            {
                "type": "sensor_data",
                "node_id": 1,
                "payload": { "temperature": 25.3, "humidity": 60.1 }
            }
        """
        try:
            packet = json.loads(raw_data)
        except json.JSONDecodeError as e:
            print(f"❌ [PacketRouter] JSON 파싱 실패: {e}")
            return

        packet_type = packet.get("type")

        if packet_type in self._route_table:
            print(f"📨 [PacketRouter] '{packet_type}' 패킷 수신 → 핸들러 호출")
            self._route_table[packet_type](packet)
        else:
            print(f"⚠️ [PacketRouter] 알 수 없는 패킷 타입: {packet_type}")

    # ──────────── 개별 핸들러 ────────────

    def _handle_sensor_data(self, packet: dict):
        """
        센서 데이터 패킷 처리.
        payload에서 온도/습도 값을 꺼내 FarmEnvManager에게 전달한다.
        """
        node_id = packet.get("node_id")
        payload = packet.get("payload", {})
        temperature = payload.get("temperature")
        humidity = payload.get("humidity")

        print(f"🌡️  [PacketRouter] 센서 데이터 → 노드 {node_id}: "
              f"온도={temperature}°C, 습도={humidity}%")

        # FarmEnvManager에게 환경 데이터 전달하여 판단 로직 실행
        self.farm_env_manager.update_environment(node_id, temperature, humidity)

    def _handle_robot_status(self, packet: dict):
        """
        로봇 상태 업데이트 패킷 처리.
        로봇의 현재 위치, 배터리, 상태 등을 RobotManager에게 전달한다.
        """
        robot_id = packet.get("robot_id")
        payload = packet.get("payload", {})

        print(f"🤖 [PacketRouter] 로봇 상태 업데이트 → 로봇 {robot_id}")

        # RobotManager에게 로봇 상태 정보 갱신 요청
        self.robot_manager.update_robot_status(robot_id, payload)

    def _handle_robot_response(self, packet: dict):
        """
        로봇 작업 응답 패킷 처리.
        로봇이 할당된 Task를 완료했는지, 실패했는지 결과를 처리한다.
        """
        robot_id = packet.get("robot_id")
        result = packet.get("result")  # "success" 또는 "fail"

        print(f"📬 [PacketRouter] 로봇 작업 응답 → 로봇 {robot_id}, 결과: {result}")

        # TODO: 로봇 작업 완료/실패에 따른 후속 처리 로직
        # - 성공 시: 큐에서 다음 Task 할당
        # - 실패 시: 재시도 또는 에러 로깅
        self.robot_manager.handle_task_result(robot_id, result)
