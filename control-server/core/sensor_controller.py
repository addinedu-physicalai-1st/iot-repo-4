"""
센서 데이터 처리 및 제어 로직
- ESP32에서 수신된 센서 데이터를 DB에 저장하고, 환경 기준값에 따라 제어 명령을 반환합니다.
- 원본: integrated_server.py → process_sensor_and_control()
"""
from datetime import datetime, timedelta, timezone
from database.db_config import get_db_connection

# 전역 상태 (이전 상태와 비교하여 변경 시 이벤트 로그)
previous_states = {'val': {}, 'fan': {}, 'led': {}}

# 실시간 데이터 캐시 (대시보드 API에서 사용)
latest_data = {}

# 수동 제어 오버라이드 캐시 (대시보드에서 ON/OFF 시 ESP32로 명령 전달)
manual_overrides = {}

# 로그 출력 억제 플래그 (CLI 입력 중 사용)
log_suppressed = False

# ANSI 색상 코드
COLOR_RESET = "\033[0m"
COLOR_YELLOW = "\033[33m" # Standard Yellow
COLOR_BLUE = "\033[34m"   # Standard Blue
COLOR_RED = "\033[31m"    # Standard Red
COLOR_CYAN = "\033[36m"


def process_sensor_and_control(p_id, node_id, dyn_ctrl_id, curr_temp, curr_humi, curr_light, curr_water=0):
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

            # 4-1. 수동 제어 오버라이드 반영
            ui_node = node_id.lower()
            if ui_node in manual_overrides:
                override = manual_overrides[ui_node]
                if 'led' in override: command_led = override['led']
                if 'val' in override: command_val = override['val']
                if 'fan' in override: command_fan = override['fan']

            # 5. 정규화된 액추에이터 로그 (PUMP=1, FAN=2, LED=4)
            for a_type, cmd_key, state_val in [(1, 'val', command_val), (2, 'fan', command_fan), (4, 'led', command_led)]:
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
                    print(f"📝 [이벤트] {node_id} >> {cmd_key.upper()}:{pure_state}")

        conn.commit()

        # 6. 로깅 및 캐시 업데이트
        log_suffix = f"({'inbound' if p_id==10 else 'outbound'}) " if p_id in [10, 99] else ""
        water_str = f" | 수위:{curr_water:4.1f}%" if curr_water is not None else ""
        
        # 색상 적용 (출력용)
        disp_led = f"{COLOR_YELLOW}{command_led}{COLOR_RESET}" if command_led.endswith("_ON") else command_led
        disp_val = f"{COLOR_BLUE}{command_val}{COLOR_RESET}" if command_val.endswith("_ON") else command_val
        disp_fan = f"{COLOR_RED}{command_fan}{COLOR_RESET}" if command_fan.endswith("_ON") else command_fan
        
        if not log_suppressed:
            print(f"📡 [{node_id}] {log_suffix}온도:{curr_temp:4.1f}℃ | 습도:{curr_humi:4.1f}% | 조도:{curr_light:>4}{water_str} >> 📤 {disp_led}, {disp_val}, {disp_fan}")

        latest_data[node_id] = {
            "temp": round(curr_temp, 1) if isinstance(curr_temp, (int, float)) else curr_temp,
            "humi": round(curr_humi, 1) if isinstance(curr_humi, (int, float)) else curr_humi,
            "light": curr_light, 
            "water": curr_water,
            "led": command_led, "val": command_val, "fan": command_fan,
            "last_seen": kst_now.strftime('%H:%M:%S')
        }
        return command_led, command_val, command_fan

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"❌ DB 처리 에러: {e}")
        return "LED_OFF", "VAL_OFF", "FAN_OFF"
    finally:
        if conn:
            conn.close()


def log_manual_actuator_to_db(node_id, act_id, state_val):
    """CLI에서 호출되는 수동 제어 기록 저장 기능"""
    kst_now = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=9)
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 1. 제어기 ID (노드 ID와 1:1)
            cursor.execute("SELECT controller_id FROM nursery_controllers WHERE node_id=%s", (node_id,))
            ctrl = cursor.fetchone()
            if not ctrl: return
            c_id = ctrl['controller_id'] if isinstance(ctrl, dict) else ctrl[0]

            # 2. 액추에이터 ID 확보
            cursor.execute("SELECT actuator_id FROM nursery_actuators WHERE controller_id=%s AND actuator_type_id=%s", (c_id, act_id))
            act = cursor.fetchone()
            if not act:
                cursor.execute("INSERT INTO nursery_actuators (controller_id, actuator_type_id, pin_number) VALUES (%s, %s, 0)", (c_id, act_id))
                a_id = cursor.lastrowid
            else:
                a_id = act['actuator_id'] if isinstance(act, dict) else act[0]

            # 3. 로그 저장 (Trigger 2 = MANUAL)
            cursor.execute(
                "INSERT INTO nursery_actuator_logs (actuator_id, state_value, trigger_id, logged_at) VALUES (%s, %s, 2, %s)",
                (a_id, str(state_val), kst_now)
            )
        conn.commit()
    except Exception as e:
        print(f"⚠️ [Log Manual] 저장 에러: {e}")
    finally:
        conn.close()


def load_latest_sensor_data_from_db():
    """서버 기동 시 DB의 최신 센서/구동기 상태를 메모리 캐시(latest_data)로 로드합니다."""
    conn = get_db_connection()
    try:
        with conn.cursor() as c:
            # 모든 육묘장 노드 목록 가져오기
            c.execute("SELECT node_id FROM nursery_controllers")
            controllers = c.fetchall()
            
            for ctrl in controllers:
                node_id = ctrl['node_id'].upper()
                c_id = ctrl['node_id']
                
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
                if temp or hum or light:
                    latest_data[node_id] = {
                        "temp": round(temp, 1) if temp else 0,
                        "humi": round(hum, 1) if hum else 0,
                        "light": int(light) if light else 0,
                        "led": led_state, 
                        "val": val_state, 
                        "fan": fan_state,
                        "last_seen": last_time.strftime('%H:%M:%S') if last_time else datetime.now().strftime('%H:%M:%S')
                    }
        print(f"🔄 [DB Init] 육묘장 최신 센서 상태 개수: {len(latest_data)}개 로드 완료")
    except Exception as e:
        print(f"⚠️ [DB Init] 캐시 로드 중 에러: {e}")
    finally:
        conn.close()

