"""
로봇/센서 TCP 소켓 서버
- 포트 8000에서 하드웨어(AGV, 육묘장 센서 등)의 TCP 연결을 수신합니다.
- CRC16-CCITT 바이너리 패킷 (SFAM Protocol)을 파싱하여 대시보드 및 DB에 반영합니다.
"""
import socket
import threading
import struct
from datetime import datetime
from database.db_config import get_db_connection
from core.node_identifier import identify_node
from core.sensor_controller import latest_data, process_sensor_and_control
from core.logger import web_log
from network.sfam_protocol import (
    SfamParser, build_packet, MSG_HEARTBEAT_REQ, MSG_HEARTBEAT_ACK,
    MSG_AGV_TELEMETRY, MSG_SENSOR_BATCH, MSG_RFID_EVENT, ID_SERVER, MSG_AGV_TASK_CMD
)

# TCP 연결된 클라이언트 소켓 관리
active_tcp_connections = {}  # { '0x01': socket, 's11': socket, ... }
last_logged_states = {}
latest_robot_state = {}

def send_actuator_command(node_id: str, actuator_id: int, value: int) -> bool:
    """
    특정 노드(예: 's11')에 연결된 소켓을 찾아 MSG_ACTUATOR_CMD 파라미터를 바이너리로 전송.
    actuator_id: 0=MODE, 1=PUMP, 2=FAN, 3=HEATER, 4=LED
    value: 0=OFF, 1=ON (또는 0~100 밝기)
    """
    node_key = node_id.lower()
    if node_key not in active_tcp_connections:
        web_log(f"⚠️ [TCP Server] 노드 {node_key}가 현재 오프라인입니다. 제어 명령 전송 실패.", "sys")
        return False
        
    client_socket = active_tcp_connections[node_key]
    try:
        # MSG_ACTUATOR_CMD(0x21) 구조: PayloadActuatorCmd 4바이트
        # [0] actuator_id, [1] state_value, [2] trigger_id, [3] duration_sec
        # trigger_id: 1=AUTO, 2=MANUAL, 3=SCHEDULE
        # duration_sec: 0=무기한
        payload = bytes([actuator_id, value, 2, 0])  # trigger=MANUAL(2), duration=무기한(0)
        pkt = build_packet(0x21, ID_SERVER, 0xFF, 0, payload)
        client_socket.sendall(pkt)
        if actuator_id == 4:  # LED
            print(f"💡 [제어 명령 전송] {node_key.upper()} LED 밝기 → {value}% 전송 성공! (payload={list(payload)})")
        else:
            print(f"👉 [제어 명령 전송] {node_key.upper()} ACTUATOR({actuator_id}) → {'ON' if value else 'OFF'} 전송 성공!")
        return True
    except Exception as e:
        print(f"❌ [TCP Server] 노드 {node_key} 명령 전송 오류: {e}")
        # 오류 시 연결 제거 처리도 고려 가능
        return False

def handle_hardware_client(client_socket, addr):
    """하드웨어 TCP 클라이언트 (바이너리 프로토콜) 수신 스레드"""
    web_log(f"📡 [TCP Server] 하드웨어 접속: {addr}", "sys")
    
    parser = SfamParser()
    client_id = None
    display_name = f"{addr}"
    
    while True:
        try:
            data = client_socket.recv(4096)
            if not data:
                break
                
            for b in data:
                packet = parser.process_byte(b)
                if packet:
                    msg_type = packet['msg_type']
                    src_id = packet['src_id']
                    seq = packet['seq']
                    payload = packet['payload']
                    
                    # Register or update connection mapping for this src_id
                    client_id = f"0x{src_id:02X}"
                    if client_id not in active_tcp_connections:
                        active_tcp_connections[client_id] = client_socket
                    
                    # AGV 매핑 (0x01 등 로봇 ID일 경우 'R01' 등으로도 등록)
                    if src_id < 0x10:  # 로봇은 0x01~0x0F 대역 사용
                        agv_key = "R01" if src_id == 0x01 else f"R{src_id:02d}"
                        if agv_key not in active_tcp_connections:
                            active_tcp_connections[agv_key] = client_socket
                        display_name = f"[{agv_key}]"
                    else:
                        _, node_id, _ = identify_node(src_id)
                        if node_id:
                            node_key = node_id.lower()
                            if node_key not in active_tcp_connections:
                                active_tcp_connections[node_key] = client_socket
                            display_name = f"[{node_id.upper()}]"
                        else:
                            display_name = f"[{client_id}]"
                            
                    # 1. 하트비트 요청 (0x01)
                    if msg_type == MSG_HEARTBEAT_REQ:
                        ack_payload = bytes([1, 0]) # ONLINE
                        ack_pkt = build_packet(MSG_HEARTBEAT_ACK, ID_SERVER, src_id, seq, ack_payload)
                        client_socket.sendall(ack_pkt)
                    
                    # 2. 로봇 텔레메트리 데이터 (0x10)
                    elif msg_type == MSG_AGV_TELEMETRY:
                        # 0: status, 1: batt, 2: node_idx, 3: next_node_idx, 4: task_id, 5: line_mask, 6: pwm, 7: err
                        if len(payload) >= 8:
                            batt = payload[1]
                            node_idx = payload[2]
                            next_node_idx = payload[3]  # 다음 목적지 노드 (0=없음)
                            
                            # 로봇 DB ID 매핑
                            agv_db_id = "R01" if src_id == 0x01 else f"R{src_id:02d}"
                            
                            # Node Name 매핑 함수
                            def idx_to_node_str(idx):
                                if 1 <= idx <= 4:
                                    return f"a{idx:02d}"
                                elif 5 <= idx <= 7:
                                    return f"s{idx:02d}"
                                elif 8 <= idx <= 10:
                                    return f"r{idx:02d}"
                                elif 11 <= idx <= 13:
                                    return f"s{idx:02d}"
                                elif 14 <= idx <= 16:
                                    return f"r{idx:02d}"
                                return None

                            node_str = idx_to_node_str(node_idx) or f"node-{node_idx:02d}"
                            next_node_str = idx_to_node_str(next_node_idx)  # None if 0 or invalid
                                
                            # API용 최신 상태 캐시 저장
                            latest_robot_state[agv_db_id] = {
                                "battery": batt,
                                "node": node_str,
                                "next_node": next_node_str,
                                "loaded": False
                            }
                            
                            # DB 로깅 (current_node FK: farm_nodes.node_id 형식 a01, s06 등)
                            node_for_db = node_str if (1 <= node_idx <= 16) else None
                            conn = get_db_connection()
                            try:
                                with conn.cursor() as cursor:
                                    agv_db_id = f"R{src_id:02d}"
                                    cursor.execute(
                                        "INSERT IGNORE INTO agv_robots (agv_id, status_id) VALUES (%s, 1)",
                                        (agv_db_id,)
                                    )
                                    if node_for_db:
                                        cursor.execute(
                                            "INSERT IGNORE INTO farm_nodes (node_id, node_name, node_type_id, current_variety_id) VALUES (%s, %s, 2, 1)",
                                            (node_for_db, node_for_db)
                                        )
                                    cursor.execute(
                                        "INSERT INTO agv_telemetry_logs (agv_id, current_node, logged_at) VALUES (%s, %s, %s)",
                                        (agv_db_id, node_for_db, datetime.now())
                                    )
                                conn.commit()
                            except Exception as e:
                                print(f"DB Error: {e}")
                            finally:
                                conn.close()
                                
                    # 3. 육묘장 센서 배치 (0x20)
                    elif msg_type == MSG_SENSOR_BATCH:
                        if len(payload) > 0:
                            count = payload[0]
                            idx = 1
                            temp = hum = light = water = 0
                            
                            for _ in range(count):
                                if idx + 3 >= len(payload): break
                                s_id = payload[idx]
                                # 24bit signed int 변환 (대충)
                                val_bytes = bytes([0]) + payload[idx+1:idx+4]
                                raw_val = struct.unpack('>i', val_bytes)[0]
                                
                                if s_id == 0x01: temp = raw_val / 100.0
                                elif s_id == 0x02: hum = raw_val / 100.0
                                elif s_id == 0x03: light = float(raw_val)
                                elif s_id == 0x04: water = raw_val / 10.0
                                idx += 4
                            
                            # 노드 정보 식별
                            p_id, node_id, dyn_ctrl_id = identify_node(src_id)
                            
                            # 로직 통합: process_sensor_and_control 호출 (DB 저장 및 제어값 계산 포함)
                            process_sensor_and_control(p_id, node_id, dyn_ctrl_id, temp, hum, light, water, seq=seq, count=count)
                                
                    # 4. AGV 로봇이 통신으로 보낸 RFID 태그 인식 이벤트 (0x24)
                    elif msg_type == MSG_RFID_EVENT:
                        print(f"🔗 [AGV RFID EVENT] 수신 Payload: {payload.hex()}")
                        # 가정한 payload 포맷: 카드 UID 문자열 혹은 바이트
                        # 앞뒤 공백 제거나 널바이트 처리 후 문자열 변환
                        scanned_uid = payload.decode('ascii', errors='ignore').strip('\x00').strip().upper()
                        print(f"🤖 [AGV RFID 스캔] 로봇: {src_id:02X}, 카드 UID: {scanned_uid}")
                        
                        conn = get_db_connection()
                        try:
                            with conn.cursor() as cursor:
                                agv_db_id = f"R{src_id:02d}"
                                
                                # 1단계: 스캔한 카드가 어느 트레이인지 확인
                                cursor.execute("SELECT tray_id FROM trays WHERE nfc_uid = %s", (scanned_uid,))
                                tray_info = cursor.fetchone()
                                
                                if tray_info:
                                    # 2단계: 이 로봇이 현재 수행 중인(또는 대기 중인) 트레이 관련 운송 작업 찾기
                                    # PENDING(0) 이나 IN_PROGRESS(1) 인 작업
                                    cursor.execute("""
                                        SELECT task_id, source_node, destination_node, task_status 
                                        FROM transport_tasks 
                                        WHERE agv_id = %s AND task_status IN (0, 1)
                                    """, (agv_db_id,))
                                    active_task = cursor.fetchone()
                                    
                                    if active_task:
                                        t_id = active_task['task_id']
                                        t_status = active_task['task_status']
                                        src_node = active_task['source_node']
                                        dst_node = active_task['destination_node']
                                        
                                        # 최신 텔레메트리에서 이 로봇의 위치 짐작 (현재 노드)
                                        # (임시 방편: DB의 agv_telemetry_logs 가장 최신값 확인)
                                        cursor.execute("SELECT current_node FROM agv_telemetry_logs WHERE agv_id = %s ORDER BY log_id DESC LIMIT 1", (agv_db_id,))
                                        last_log = cursor.fetchone()
                                        curr_node = last_log['current_node'] if last_log else None
                                        
                                        print(f"   -> [상태 검사] 현재AGV위치: {curr_node}, 목적지: {dst_node}, 작업상태: {t_status}")
                                        
                                        # 시나리오 A: 출발지에서 픽업 확인 (PENDING(0) -> IN_PROGRESS(1))
                                        if t_status == 0:
                                            print(f"   -> [픽업 확인] AGV가 출발지({src_node})에서 트레이 탑재 완료. 이동 시작.")
                                            cursor.execute("UPDATE transport_tasks SET task_status = 1, started_at = %s WHERE task_id = %s", (datetime.now(), t_id))
                                            
                                            # 👉 로봇에게 목적지로 이동 명령(MSG_AGV_TASK_CMD) 하달
                                            try:
                                                # 목적지 노드 번호 추출 (예: 's06' -> 6, 'r08' -> 8)
                                                dst_idx = int(''.join(filter(str.isdigit, dst_node)))
                                                
                                                # Payload 구성: [TaskID_H, TaskID_L, Src(0), 0, 0, Dst(dst_idx), 0, 0, 0, 0] (총 10바이트)
                                                payload = bytearray(10)
                                                payload[0] = (t_id >> 8) & 0xFF
                                                payload[1] = t_id & 0xFF
                                                payload[5] = dst_idx & 0xFF
                                                
                                                # 시퀀스는 임시로 0 사용 (로봇 펌웨어에선 현재 크게 체크 안함)
                                                task_pkt = build_packet(MSG_AGV_TASK_CMD, ID_SERVER, src_id, 0, bytes(payload))
                                                client_socket.sendall(task_pkt)
                                                print(f"   -> [명령 하달] 로봇 {src_id:02X}에게 {dst_node}(Idx:{dst_idx})로 이동 명령 전송 완료!")
                                            except Exception as e:
                                                print(f"   -> [명령 하달 실패] 패킷 전송 오류: {e}")
                                            
                                        # 시나리오 B: 목적지에서 하차 확인 (IN_PROGRESS(1) -> DONE(2))
                                        elif t_status == 1:
                                            # (실제로는 curr_node == dst_node 여부도 검사해야 하나, 단순화)
                                            print(f"   -> [도착/하차 확인] AGV가 목적지({dst_node})에 트레이 안착 완료. (Task: {t_id})")
                                            cursor.execute("UPDATE transport_tasks SET task_status = 2, completed_at = %s WHERE task_id = %s", (datetime.now(), t_id))
                                            # 빈자리 1개 채움 기록
                                            cursor.execute("UPDATE farm_nodes SET current_quantity = current_quantity + 1 WHERE node_id = %s", (dst_node,))
                                            # 트레이 상태 GROWING(5) 으로 업데이트
                                            cursor.execute("UPDATE trays SET tray_status = 1, growth_stage = 5 WHERE nfc_uid = %s", (scanned_uid,))
                                            
                                    else:
                                        print("   -> 할당된 작업이 없는 상태에서 스캔되었습니다.")
                                else:
                                    print("   -> 시스템(trays 테이블)에 등록되지 않은 카드입니다.")
                                    
                            conn.commit()
                        except Exception as e:
                            print(f"AGV RFID DB Error: {e}")
                        finally:
                            conn.close()
            
        except ConnectionResetError:
            web_log(f"📡 {display_name} 기기 접속 끊김 (Connection Reset)", "sys")
            break
        except Exception as e:
            print(f"[TCP Server] {display_name} Error: {e}")
            break

    if client_id and client_id in active_tcp_connections:
        del active_tcp_connections[client_id]
        # R01 매핑도 제거 (같은 소켓 참조)
        for k in list(active_tcp_connections.keys()):
            if active_tcp_connections[k] == client_socket:
                del active_tcp_connections[k]
    client_socket.close()


def tcp_robot_server():
    """하드웨어 TCP 서버 메인 루프 (포트 8000)"""
    tcp_port = 8000
    
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server_socket.bind(('0.0.0.0', tcp_port))
        server_socket.listen(5)
        print(f"\n🚀 [TCP Binary Server] 하드웨어 패킷 수신 대기 (포트: {tcp_port})")
    except OSError as e:
        print(f"\n❌ [TCP Server] 포트 {tcp_port} 사용 불가: {e}")
        return

    while True:
        try:
            client_socket, addr = server_socket.accept()
            threading.Thread(target=handle_hardware_client, args=(client_socket, addr), daemon=True).start()
        except:
            break
