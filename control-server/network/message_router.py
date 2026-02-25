"""
message_router.py
=================
수신된 JSON 메시지를 파싱하고, 메시지 타입(type/cmd)에 따라
적절한 처리 함수(핸들러)로 라우팅하는 중앙 메시지 라우터.

[통신 규격]
  ● UDP 수신 (육묘장/AGV → 서버):
    - 센서:       {"type": "SENSOR", "controller_id": "...", "sensor_id": 1, "value": 24.5}
    - AGV 상태:   {"type": "AGV_STATE", "agv_id": "R01", "pos_x": 120, "pos_y": 350, "battery": 80}
    - RFID 리딩:  {"type": "RFID_READ", "rfid_value": "...", "station_node_id": "..."}
    - 하트비트:   {"type": "HEARTBEAT", "controller_id": "..."}

  ● TCP 수신 (AGV/GUI → 서버):
    - 이동:   {"cmd": "MOVE", "target_node": "NODE-A1-001"}
    - 작업:   {"cmd": "TASK", "action": "INBOUND"|"OUTBOUND", "source": "...", "dest": "...", "variety_id": 1}
    - 수동:   {"cmd": "MANUAL", "device": "FAN", "state": "ON", "actuator_id": 1}
    - 모드:   {"cmd": "SET_MODE", "controller_id": "...", "mode": "AUTO"|"MANUAL"}

  ● TCP 응답 (서버 → AGV/GUI):
    - {"status": "SUCCESS", "msg": "..."}
"""

import json


class MessageRouter:
    """
    수신된 JSON 데이터를 파싱한 뒤,
    'type' 필드(UDP) 또는 'cmd' 필드(TCP)에 따라
    등록된 핸들러 함수로 분배하는 라우터 클래스.

    의존성 (SystemController에서 주입):
        - AgvManager              : AGV 상태 업데이트
        - NurseryControllerManager: 센서 데이터 / 하트비트 처리
        - SearchDeviceManager     : RFID 리딩 처리
        - TransportTaskQueue      : 운송 작업 큐 관리
    """

    def __init__(self, agv_manager, nursery_ctrl_manager, search_device_manager, task_queue):
        """
        Args:
            agv_manager          : AgvManager 인스턴스
            nursery_ctrl_manager : NurseryControllerManager 인스턴스
            search_device_manager: SearchDeviceManager 인스턴스
            task_queue           : TransportTaskQueue 인스턴스
        """
        self.agv_manager = agv_manager
        self.nursery_ctrl_manager = nursery_ctrl_manager
        self.search_device_manager = search_device_manager
        self.task_queue = task_queue

        # ── UDP 메시지 타입 → 핸들러 매핑 ──
        self._udp_handlers: dict[str, callable] = {
            "SENSOR":     self._on_sensor_data,
            "AGV_STATE":  self._on_agv_state,
            "RFID_READ":  self._on_rfid_read,
            "HEARTBEAT":  self._on_heartbeat,
        }

        # ── TCP 명령 타입 → 핸들러 매핑 ──
        self._tcp_handlers: dict[str, callable] = {
            "MOVE":     self._on_cmd_move,
            "TASK":     self._on_cmd_task,
            "MANUAL":   self._on_cmd_manual,
            "SET_MODE": self._on_cmd_set_mode,
        }

    # ============================================================
    #  공통 JSON 파싱
    # ============================================================

    def _parse_json(self, raw_data: str) -> dict | None:
        """원시 문자열을 JSON 딕셔너리로 파싱한다."""
        try:
            return json.loads(raw_data)
        except json.JSONDecodeError as e:
            print(f"❌ [MessageRouter] JSON 파싱 실패: {e}")
            return None

    # ============================================================
    #  UDP 라우팅
    # ============================================================

    def route_udp(self, raw_data: str):
        """UDP 수신 데이터를 파싱하고 type에 따라 핸들러를 호출한다."""
        message = self._parse_json(raw_data)
        if message is None:
            return

        msg_type = message.get("type")
        if msg_type in self._udp_handlers:
            print(f"📡 [UDP] '{msg_type}' 메시지 수신 → 핸들러 호출")
            self._udp_handlers[msg_type](message)
        else:
            print(f"⚠️ [UDP] 알 수 없는 메시지 타입: {msg_type}")

    # ============================================================
    #  TCP 라우팅
    # ============================================================

    def route_tcp(self, raw_data: str) -> dict:
        """TCP 수신 데이터를 파싱하고 cmd에 따라 핸들러를 호출한다."""
        message = self._parse_json(raw_data)
        if message is None:
            return {"status": "FAIL", "msg": "JSON 파싱 실패"}

        cmd = message.get("cmd")
        if cmd in self._tcp_handlers:
            print(f"📨 [TCP] '{cmd}' 명령 수신 → 핸들러 호출")
            return self._tcp_handlers[cmd](message)
        else:
            print(f"⚠️ [TCP] 알 수 없는 명령: {cmd}")
            return {"status": "FAIL", "msg": f"알 수 없는 명령: {cmd}"}

    # ============================================================
    #  UDP 핸들러
    # ============================================================

    def _on_sensor_data(self, message: dict):
        """
        센서 데이터 처리.
        수신: {"type": "SENSOR", "controller_id": "...", "sensor_id": 1, "value": 24.5}
        """
        controller_id = message.get("controller_id")
        sensor_id = message.get("sensor_id")
        value = message.get("value")
        print(f"🌡️ [핸들러] 센서 → 제어기: {controller_id}, 센서: {sensor_id}, 값: {value}")

        # NurseryControllerManager에게 전달
        self.nursery_ctrl_manager.handle_sensor_data(controller_id, sensor_id, value)

    def _on_agv_state(self, message: dict):
        """
        AGV 상태 업데이트.
        수신: {"type": "AGV_STATE", "agv_id": "R01", "pos_x": 120, "pos_y": 350, "battery": 80}
        """
        agv_id = message.get("agv_id")
        payload = {k: v for k, v in message.items() if k not in ("type", "agv_id")}
        print(f"🤖 [핸들러] AGV 상태 → ID: {agv_id}")

        self.agv_manager.update_agv_status(agv_id, payload)

    def _on_rfid_read(self, message: dict):
        """
        RFID 리딩 처리 (입고장).
        수신: {"type": "RFID_READ", "rfid_value": "...", "station_node_id": "..."}
        """
        rfid_value = message.get("rfid_value")
        station_node_id = message.get("station_node_id")
        print(f"📡 [핸들러] RFID 리딩 → 값: {rfid_value}, 입고장: {station_node_id}")

        self.search_device_manager.handle_rfid_read(rfid_value, station_node_id)

    def _on_heartbeat(self, message: dict):
        """
        제어기 하트비트.
        수신: {"type": "HEARTBEAT", "controller_id": "..."}
        """
        controller_id = message.get("controller_id")
        self.nursery_ctrl_manager.handle_heartbeat(controller_id)

    # ============================================================
    #  TCP 핸들러
    # ============================================================

    def _on_cmd_move(self, message: dict) -> dict:
        """
        이동 명령.
        수신: {"cmd": "MOVE", "target_node": "NODE-A1-001"}

        TODO (팀원 구현):
            1) target_node 좌표를 DB에서 조회
            2) AGV에 TCP로 이동 명령 전송
        """
        target_node = message.get("target_node")
        print(f"🚗 [핸들러] 이동 명령 → 목표: {target_node}")
        return {"status": "SUCCESS", "msg": f"{target_node}으로 이동 명령 전달"}

    def _on_cmd_task(self, message: dict) -> dict:
        """
        운송 작업 명령.
        수신: {"cmd": "TASK", "action": "INBOUND"|"OUTBOUND", "source": "...", "dest": "...", "variety_id": 1}

        TODO (팀원 구현):
            1) action에 따라 TransportTaskQueue에 Task 생성
            2) AGV에 작업 할당
        """
        action = message.get("action")
        source = message.get("source", "")
        dest = message.get("dest", "")
        variety_id = message.get("variety_id")
        print(f"🎯 [핸들러] 운송 작업 → {action}: {source} → {dest}")

        if action == "OUTBOUND":
            self.task_queue.create_outbound_task(source, dest, variety_id)
        elif action == "INBOUND":
            self.task_queue.create_inbound_task(source, dest, variety_id)

        return {"status": "SUCCESS", "msg": f"{action} 작업 등록 완료"}

    def _on_cmd_manual(self, message: dict) -> dict:
        """
        수동 제어 명령.
        수신: {"cmd": "MANUAL", "device": "FAN", "state": "ON", "actuator_id": 1}
        """
        device = message.get("device")
        state = message.get("state")
        actuator_id = message.get("actuator_id")
        print(f"🔧 [핸들러] 수동 제어 → {device}: {state}")

        if actuator_id:
            self.nursery_ctrl_manager.manual_actuator_control(actuator_id, state)

        return {"status": "SUCCESS", "msg": f"{device} → {state} 제어 완료"}

    def _on_cmd_set_mode(self, message: dict) -> dict:
        """
        육묘장 제어 모드 전환 (SR-29).
        수신: {"cmd": "SET_MODE", "controller_id": "...", "mode": "AUTO"|"MANUAL"}
        """
        controller_id = message.get("controller_id")
        mode = message.get("mode")
        print(f"⚙️ [핸들러] 모드 전환 → 제어기: {controller_id}, 모드: {mode}")

        self.nursery_ctrl_manager.set_control_mode(controller_id, mode)
        return {"status": "SUCCESS", "msg": f"제어기 {controller_id} → {mode} 모드"}
