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


def process_sensor_and_control(p_id, node_id, dyn_ctrl_id, curr_temp, curr_humi, curr_light):
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

            # 2. 정규화된 센서 데이터 삽입 (Temp=1, Humi=2, Light=3)
            for s_type, val in [(1, curr_temp), (2, curr_humi), (3, curr_light)]:
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
            t_set, h_set, l_set = (env['opt_temp_day'], env['opt_humidity'], env['opt_light_dli']) if env else (22, 58, 2000)

            # 4. 제어 로직 (자동 로직)
            command_led = "LED_ON" if curr_light < l_set else "LED_OFF"
            command_val = "VAL_ON" if curr_humi < h_set else "VAL_OFF"
            command_fan = "FAN_ON" if curr_temp > t_set else "FAN_OFF"

            # 4-1. 수동 제어 오버라이드 반영
            ui_node = node_id.lower()
            if ui_node in manual_overrides:
                override = manual_overrides[ui_node]
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
                    print(f"📝 [이벤트] {node_id} >> {cmd_key.upper()}:{pure_state}")

        conn.commit()

        # 6. 로깅 및 캐시 업데이트
        log_suffix = f"({'inbound' if p_id==10 else 'outbound'}) " if p_id in [10, 99] else ""
        print(f"📡 [{node_id}] {log_suffix}온도:{curr_temp:,}℃ | 습도:{curr_humi:,}% | 조도:{curr_light:,} >> 📤 {command_led}, {command_val}, {command_fan}")

        latest_data[node_id] = {
            "temp": round(curr_temp, 1) if isinstance(curr_temp, (int, float)) else curr_temp,
            "humi": round(curr_humi, 1) if isinstance(curr_humi, (int, float)) else curr_humi,
            "light": curr_light, "led": command_led, "val": command_val, "fan": command_fan,
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
