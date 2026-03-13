"""
센서 데이터 처리 및 제어 로직
- ESP32에서 수신된 센서 데이터를 DB에 저장하고, 환경 기준값에 따라 제어 명령을 반환합니다.
- 원본: integrated_server.py → process_sensor_and_control()
"""
from datetime import datetime, timedelta, timezone
from database.db_config import get_db_connection
from core.logger import web_log

# 전역 상태 (이전 상태와 비교하여 변경 시 이벤트 로그)
previous_states = {'val': {}, 'fan': {}, 'led': {}}

# 실시간 데이터 캐시 (대시보드 API에서 사용)
latest_data = {}

# 수동 제어 오버라이드 캐시 (대시보드에서 ON/OFF 시 ESP32로 명령 전달)
manual_overrides = {}

# CLI / 로그 제어 플래그
log_suppressed = False

# ANSI 색상 코드
COLOR_RESET = "\033[0m"
COLOR_YELLOW = "\033[33m" # Standard Yellow
COLOR_BLUE = "\033[34m"   # Standard Blue
COLOR_RED = "\033[31m"    # Standard Red
COLOR_CYAN = "\033[36m"
COLOR_GRAY = "\033[90m"

def print_node_status(node_id, temp, humi, light, water, led, val, fan, seq=None, count=None, suffix="", source=None):
    """터미널에 노드 상태를 일관된 포맷으로 출력합니다."""
    if log_suppressed: return
    
    if seq is not None:
        seq_str = f" [SEQ:{seq}]"
    else:
        # 수동 명령의 경우 타임스탬프 기반 ID 생성 (KST 기준)
        kst_now = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=9)
        seq_str = f" [CMD:{kst_now.strftime('%Y%m%d-%H%M%S')}]"
    
    cnt_str = f" (cnt:{count})" if count is not None else ""
    water_str = f" | 수위:{water:4.1f}%" if water is not None else ""
    
    # 색상 적용
    disp_led = f"{COLOR_YELLOW}{led}{COLOR_RESET}" if led.endswith("_ON") or (led.startswith("LED_") and any(char.isdigit() for char in led) and "0" not in led) else led
    disp_val = f"{COLOR_BLUE}{val}{COLOR_RESET}" if val.endswith("_ON") else val
    disp_fan = f"{COLOR_RED}{fan}{COLOR_RESET}" if fan.endswith("_ON") else fan
    
    src_info = f" {COLOR_GRAY}({source}){COLOR_RESET}" if source else ""
    
    # 모드 판별 (Latest Data Cache에서 확인)
    is_manual = False
    ui_node = node_id.lower()
    if ui_node in latest_data:
        m_val = latest_data[ui_node].get('mode', '')
        if 'OFF' in m_val or 'MANUAL' in m_val: is_manual = True
    
    mode_label = f"[{COLOR_GRAY}MANUAL{COLOR_RESET}]" if is_manual else f"[{COLOR_CYAN}AUTO{COLOR_RESET}]"
    
    msg = f"📡 [{node_id.upper()}] {'[MANUAL]' if is_manual else '[AUTO]'}{seq_str}{cnt_str} {suffix}온도:{temp:4.1f}℃ | 습도:{humi:4.1f}% | 조도:{light:>4}{water_str} >> 📤 {led}, {val}, {fan}{src_info}"
    web_log(msg, "sensor")
    
    # 터미널용 색상 입힌 출력은 유지 (web_log 내부의 print는 기본 출력이므로 중복 방지를 위해 여기서는 컬러 버전만 직접 출력하거나 조정 필요)
    # 이미 web_log가 print를 수행하므로, 여기서는 컬러링된 버전만 print하고 web_log는 데이터만 쌓음
    # print(f"📡 [{node_id.upper()}] {mode_label}{seq_str}{cnt_str} {suffix}온도:{temp:4.1f}℃ | 습도:{humi:4.1f}% | 조도:{light:>4}{water_str} >> 📤 {disp_led}, {disp_val}, {disp_fan}{src_info}")

def process_sensor_and_control(p_id, node_id, dyn_ctrl_id, curr_temp, curr_humi, curr_light, curr_water=0, seq=None, count=None):
    """
    신규 스키마의 분리된 센서/구동기 테이블에 데이터를 안전하게 저장하고 제어값을 반환합니다.
    
    Returns:
        tuple: (command_led, command_val, command_fan)
    """
    kst_now = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=9)
    conn = None

    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # 1. 노드 및 제어기 확보
            cursor.execute("""
                INSERT IGNORE INTO farm_nodes (node_id, node_name, node_type_id, current_variety_id) 
                VALUES (%s, %s, 1, 1)
            """, (node_id, node_id))

            cursor.execute("""
                INSERT IGNORE INTO nursery_controllers (controller_id, node_id, device_status) 
                VALUES (%s, %s, 1)
            """, (dyn_ctrl_id, node_id))

            # 하트비트 갱신
            cursor.execute("""
                UPDATE nursery_controllers 
                SET last_heartbeat=%s, device_status=1 
                WHERE controller_id=%s
            """, (kst_now, dyn_ctrl_id))

            # 2. 정규화된 센서 데이터 삽입 (Temp=1, Humi=2, Light=3, Water=4)
            sensor_data = [(1, curr_temp), (2, curr_humi), (3, curr_light)]
            if curr_water is not None:
                sensor_data.append((4, curr_water))

            for s_type, val in sensor_data:
                cursor.execute(
                    "SELECT sensor_id FROM nursery_sensors WHERE controller_id=%s AND sensor_type_id=%s",
                    (dyn_ctrl_id, s_type)
                )
                row = cursor.fetchone()

                if row:
                    s_id = row['sensor_id'] if isinstance(row, dict) else row[0]
                else:
                    cursor.execute(
                        "INSERT INTO nursery_sensors (controller_id, sensor_type_id, pin_number) VALUES (%s, %s, 0)",
                        (dyn_ctrl_id, s_type)
                    )
                    s_id = cursor.lastrowid

                cursor.execute(
                    "INSERT INTO nursery_sensor_logs (sensor_id, value, measured_at) VALUES (%s, %s, %s)",
                    (s_id, val, kst_now)
                )

            # 3. 환경 기준값 (seedling_varieties 참조)
            cursor.execute("""
                SELECT opt_temp_day, opt_humidity, opt_light_dli 
                FROM farm_nodes fn 
                JOIN seedling_varieties sv ON fn.current_variety_id = sv.variety_id 
                WHERE fn.node_id = %s
            """, (node_id,))
            env = cursor.fetchone()
            
            # DB에 값이 있더라도 개별 컬럼이 NULL일 수 있으므로 각각 체크하여 기본값 부여
            if env:
                t_set = env['opt_temp_day'] if env['opt_temp_day'] is not None else 22.0
                h_set = env['opt_humidity'] if env['opt_humidity'] is not None else 58.0
                l_set = env['opt_light_dli'] if env['opt_light_dli'] is not None else 2000.0
            else:
                t_set, h_set, l_set = 22.0, 58.0, 2000.0

            # 4. 제어 로직 (자동 로직)
            # 사용자 요청에 따라 626 lux는 LED_OFF가 되도록 기준값 조정 (기본 l_set=2000 -> 500)
            l_set_adj = 500.0 if l_set == 2000.0 else l_set 
            command_led = "LED_ON" if (curr_light if curr_light is not None else 0) < l_set_adj else "LED_OFF"
            command_val = "VAL_ON" if (curr_humi if curr_humi is not None else 0) < h_set else "VAL_OFF"
            command_fan = "FAN_ON" if (curr_temp if curr_temp is not None else 0) > t_set else "FAN_OFF"

            # 4-1. 수동 제어 오버라이드 반영 (전체 모드 및 개별 장치)
            ui_node = node_id.lower()
            is_manual_mode = False
            
            # DB/캐시의 전체 모드가 MANUAL인 경우 체크
            if ui_node in latest_data:
                m_val = latest_data[ui_node].get('mode', '')
                if 'OFF' in m_val or 'MANUAL' in m_val: is_manual_mode = True

            if ui_node in manual_overrides:
                override = manual_overrides[ui_node]
                if 'mode' in override:
                    is_manual_mode = ('OFF' in override['mode'] or 'MANUAL' in override['mode'])
                
                # 수동 모드이거나 개별 오버라이드가 있을 때 적용
                if 'led' in override: command_led = override['led']
                if 'val' in override: command_val = override['val']
                if 'fan' in override: command_fan = override['fan']

            # 5. 정규화된 액추에이터 로그 (VAL=1, FAN=2, LED=3)
            for a_type, cmd_key, state_val in [(1, 'val', command_val), (2, 'fan', command_fan), (3, 'led', command_led)]:
                if previous_states[cmd_key].get(node_id) != state_val:
                    previous_states[cmd_key][node_id] = state_val

                    cursor.execute(
                        "SELECT actuator_id FROM nursery_actuators WHERE controller_id=%s AND actuator_type_id=%s",
                        (dyn_ctrl_id, a_type)
                    )
                    row = cursor.fetchone()

                    if row:
                        a_id = row['actuator_id'] if isinstance(row, dict) else row[0]
                    else:
                        cursor.execute(
                            "INSERT INTO nursery_actuators (controller_id, actuator_type_id, pin_number) VALUES (%s, %s, 0)",
                            (dyn_ctrl_id, a_type)
                        )
                        a_id = cursor.lastrowid

                    pure_state = state_val.split('_')[1]
                    cursor.execute(
                        "INSERT INTO nursery_actuator_logs (actuator_id, state_value, trigger_id, logged_at) VALUES (%s, %s, 1, %s)",
                        (a_id, pure_state, kst_now)
                    )
                    if not log_suppressed:
                        web_log(f"📝 [이벤트] {node_id} >> {cmd_key.upper()}:{pure_state}", "event")

        conn.commit()

        # 6. 로깅 및 캐시 업데이트
        log_suffix = f"({'inbound' if p_id==10 else 'outbound'}) " if p_id in [10, 99] else ""
        
        print_node_status(
            node_id, curr_temp, curr_humi, curr_light, curr_water, 
            command_led, command_val, command_fan, 
            seq=seq, count=count, suffix=log_suffix
        )

        latest_info = {
            "temp": round(curr_temp, 1) if isinstance(curr_temp, (int, float)) else curr_temp,
            "humi": round(curr_humi, 1) if isinstance(curr_humi, (int, float)) else curr_humi,
            "light": curr_light, 
            "water": curr_water,
            "led": command_led, "val": command_val, "fan": command_fan,
            "mode": "MODE_OFF" if is_manual_mode else "MODE_ON",
            "last_seen": kst_now.strftime('%H:%M:%S'),
            "last_updated": kst_now.timestamp() # 타임스탬프 추가
        }
        latest_data[node_id.upper()] = latest_info
        latest_data[node_id.lower()] = latest_info
        return command_led, command_val, command_fan

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"❌ DB 처리 에러: {e}")
        return "LED_OFF", "VAL_OFF", "FAN_OFF"
    finally:
        if conn:
            conn.close()


def load_latest_sensor_data_from_db():
    """서버 기동 시 DB의 최신 센서/구동기 상태를 메모리 캐시(latest_data)로 로드합니다."""
    conn = get_db_connection()
    try:
        with conn.cursor() as c:
            # 모든 육묘장 노드 목록 가져오기 (control_mode 포함)
            c.execute("SELECT node_id, control_mode FROM nursery_controllers")
            controllers = c.fetchall()
            
            for ctrl in controllers:
                node_id = ctrl['node_id'].upper()
                c_id = ctrl['node_id']
                ctrl_mode = ctrl.get('control_mode', 1) # 1=AUTO, 0=MANUAL
                
                # 센서 최신값 (Temp=1, Humi=2, Light=3)
                c.execute("""
                    SELECT 
                        s.sensor_type_id, 
                        sl.value, 
                        sl.measured_at 
                    FROM nursery_sensors s
                    JOIN nursery_sensor_logs sl ON s.sensor_id = sl.sensor_id
                    JOIN nursery_controllers nc ON s.controller_id = nc.controller_id
                    WHERE nc.node_id = %s
                    ORDER BY sl.measured_at DESC LIMIT 3
                """, (c_id,))
                
                temp = hum = light = 0
                last_time = None
                for row in c.fetchall():
                    if row['sensor_type_id'] == 1 and temp == 0: temp = row['value']
                    elif row['sensor_type_id'] == 2 and hum == 0: hum = row['value']
                    elif row['sensor_type_id'] == 3 and light == 0: light = row['value']
                    
                    if not last_time or row['measured_at'] > last_time:
                        last_time = row['measured_at']
                
                # 구동기 최신값 (VAL=1, FAN=2, LED=3)
                c.execute("""
                    SELECT 
                        a.actuator_type_id, 
                        al.state_value
                    FROM nursery_actuators a
                    JOIN nursery_actuator_logs al ON a.actuator_id = al.actuator_id
                    JOIN nursery_controllers nc ON a.controller_id = nc.controller_id
                    WHERE nc.node_id = %s
                    ORDER BY al.logged_at DESC LIMIT 3
                """, (c_id,))
                
                val_state, fan_state, led_state = "VAL_OFF", "FAN_OFF", "LED_OFF"
                act_seen = set()
                for row in c.fetchall():
                    a_type = row['actuator_type_id']
                    if a_type not in act_seen:
                        act_seen.add(a_type)
                        state_str = row['state_value']
                        if a_type == 1: val_state = f"VAL_{state_str}"
                        elif a_type == 2: fan_state = f"FAN_{state_str}"
                        elif a_type == 3: led_state = f"LED_{state_str}"
                
                # 캐시 적재
                info = {
                    "temp": round(temp, 1) if temp else 0,
                    "humi": round(hum, 1) if hum else 0,
                    "light": int(light) if light else 0,
                    "led": led_state, 
                    "val": val_state, 
                    "fan": fan_state,
                    "mode": "MODE_ON" if ctrl_mode == 1 else "MODE_OFF",
                    "last_seen": last_time.strftime('%H:%M:%S') if last_time else datetime.now().strftime('%H:%M:%S')
                }
                latest_data[node_id] = info
                latest_data[node_id.lower()] = info

        print(f"🔄 [DB Init] 육묘장 최신 센서 상태 개수: {len(latest_data)//2}개 로드 완료")
    except Exception as e:
        print(f"⚠️ [DB Init] 캐시 로드 중 에러: {e}")
    finally:
        conn.close()

def log_manual_actuator_to_db(node_id, act_id, state_val):
    """수동 제어시 액추에이터 상태를 DB에 기록합니다. (trigger_id=2: MANUAL)"""
    kst_now = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=9)
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 1. 제어기 ID 찾기 (node_id 기반)
            cursor.execute("SELECT controller_id FROM nursery_controllers WHERE node_id=%s", (node_id.lower(),))
            row = cursor.fetchone()
            if not row: return
            dyn_ctrl_id = row['controller_id'] if isinstance(row, dict) else row[0]

            # 2. 특별 처리: MODE(0)인 경우 컨트롤러 상태 테이블 업데이트
            if act_id == 0:
                cursor.execute(
                    "UPDATE nursery_controllers SET control_mode=%s WHERE controller_id=%s",
                    (state_val, dyn_ctrl_id)
                )
                conn.commit()
                return

            # 3. 액추에이터 ID 찾기 또는 생성
            cursor.execute(
                "SELECT actuator_id FROM nursery_actuators WHERE controller_id=%s AND actuator_type_id=%s",
                (dyn_ctrl_id, act_id)
            )
            row = cursor.fetchone()
            if row:
                a_id = row['actuator_id'] if isinstance(row, dict) else row[0]
            else:
                cursor.execute(
                    "INSERT INTO nursery_actuators (controller_id, actuator_type_id, pin_number) VALUES (%s, %s, 0)",
                    (dyn_ctrl_id, act_id)
                )
                a_id = cursor.lastrowid

            # 3. 로그 기록
            state_str = "ON" if state_val > 0 else "OFF"
            if act_id == 4: state_str = f"{state_val}"
            
            cursor.execute(
                "INSERT INTO nursery_actuator_logs (actuator_id, state_value, trigger_id, logged_at) VALUES (%s, %s, 2, %s)",
                (a_id, state_str, kst_now)
            )
        conn.commit()
    except Exception as e:
        print(f"⚠️ [DB Manual Log] 실패: {e}")
    finally:
        conn.close()


def execute_manual_control(node_id, device_key, state_val, trigger=2, source="Terminal"):
    """
    웹 GUI와 터미널 CLI의 수동 제어 명령을 하나로 통합 처리하는 중앙 함수입니다.
    source: 제어 주체 (예: "Terminal" 또는 IP 주소)
    """
    from network.tcp_robot_server import active_tcp_connections
    from network.sfam_protocol import build_packet, MSG_ACTUATOR_CMD, ID_SERVER
    from network.terminal_cli import log_actuator_packet
    import struct

    node_id = node_id.upper()
    device_key = device_key.lower()
    if device_key == 'pump': device_key = 'val'
    
    # 소스 구분에 따른 레이블 (출력용)
    source_label = "CLI" if source == "Terminal" else "WEB"

    # 1. 메모리 캐시 오버라이드 실시간 업데이트
    if node_id.lower() not in manual_overrides:
        manual_overrides[node_id.lower()] = {}
    
    cmd_str = f"{device_key.upper()}_{'ON' if state_val > 0 else 'OFF'}"
    if device_key == 'led': cmd_str = f"LED_{state_val}"
    
    manual_overrides[node_id.lower()] = manual_overrides.get(node_id.lower(), {})
    manual_overrides[node_id.lower()][device_key] = cmd_str
    
    if device_key not in previous_states: previous_states[device_key] = {}
    previous_states[device_key][node_id.upper()] = cmd_str
    
    # 캐시 업데이트 (대문자/소문자 모두 갱신하여 UI 연동 보장)
    for key in [node_id.upper(), node_id.lower()]:
        if key in latest_data:
            latest_data[key][device_key] = cmd_str
            if device_key == 'pump': latest_data[key]['val'] = cmd_str

    # 2. DB 로그 기록
    act_id = {"mode": 0, "pump": 1, "fan": 2, "heater": 3, "led": 4, "val": 1}.get(device_key)
    
    if act_id is not None:
        log_manual_actuator_to_db(node_id, act_id, state_val)
        
        try:
            import json
            conn = get_db_connection()
            kst_now = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=9)
            with conn.cursor() as cursor:
                # detail에 source(IP 등) 추가
                action_detail = {
                    "node_id": node_id, 
                    "device": device_key, 
                    "state": 'ON' if state_val > 0 else 'OFF', 
                    "val": state_val,
                    "source": source
                }
                user_id = 1 # 임시: admin(1) 사용 (0번 유저 부재 시 FK 방지)
                
                cursor.execute("""
                    INSERT INTO user_action_logs (user_id, action_type_id, target_id, action_detail, action_result, action_time)
                    VALUES (%s, %s, %s, %s, 1, %s)
                """, (user_id, 19, node_id, json.dumps(action_detail), kst_now))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"⚠️ [User Action Log] 실패: {e}")

    # 3. 실제 TCP 패킷 전송
    node_key = node_id.lower()
    
    # 디버깅: 현재 연결된 노드들 확인 (개발 단계용)
    # print(f"DEBUG: Checking {node_key} in {list(active_tcp_connections.keys())}")
    
    if node_key in active_tcp_connections:
        try:
            num_part = ''.join(filter(str.isdigit, node_id))
            target_id = int(num_part) + (6 if node_id.startswith('S') else 0)
            
            payload = struct.pack('BBBB', act_id, state_val, trigger, 0)
            packet = build_packet(MSG_ACTUATOR_CMD, ID_SERVER, target_id, 0, payload)
            
            # 패킷 상세 로그 (필요 시 유지)
            # log_actuator_packet(node_id, act_id, state_val, trigger, packet)
            
            # 사용자 요청 포맷 출력 (Source 포함)
            # print(f"✅ [{source_label}] 0x{target_id:02X}({node_id}) >> {device_key.upper()} {state_val} 전송 완료 (Source: {source})")
            
            # 📡 통합 포맷으로 즉시 출력하여 가독성 통일
            cache = latest_data.get(node_id.upper(), latest_data.get(node_id.lower(), {}))
            print_node_status(
                node_id, 
                cache.get('temp', 0), cache.get('humi', 0), cache.get('light', 0), cache.get('water', 0),
                cmd_str if device_key == 'led' else cache.get('led', 'LED_OFF'),
                cmd_str if device_key in ['val', 'pump'] else cache.get('val', 'VAL_OFF'),
                cmd_str if device_key == 'fan' else cache.get('fan', 'FAN_OFF'),
                source=f"{source_label}:{source}"
            )
            
            # MODE(0)인 경우 state_val이 1(AUTO), 0(MANUAL)임
            # 패킷 페이로드: [act_id, state_val, trigger, 0]
            # act_id가 None이면 전송 건너뜀 (안전 장치)
            if act_id is not None:
                active_tcp_connections[node_key].sendall(packet)
            return True, "Success"
        except Exception as e:
            return False, str(e)
    else:
        # 연결된 노드들 목록을 함께 출력하여 원인 파악 도움
        connected_nodes = ", ".join(active_tcp_connections.keys()) if active_tcp_connections else "None"
        return False, f"Node {node_id} not connected (Connected: {connected_nodes})"
