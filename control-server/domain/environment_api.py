"""
서버 환경 모니터링 API
- 통합 프론트엔드 대시보드(SPA)와 통신하기 위한 JSON API 제공
"""
import psutil
import time
import json
from flask import Blueprint, jsonify, request
from core.sensor_controller import latest_data, manual_overrides

env_bp = Blueprint('environment', __name__)

SERVER_START_TIME = time.time()

@env_bp.route('/api/system_status')
def system_status():
    """서버 시스템 및 육묘장 연결 상태 확인 API"""
    uptime = time.time() - SERVER_START_TIME
    
    # 육묘장 센서 연결 여부 (최근 데이터 갱신 시간 기준)
    now = time.time()
    nursery_connected = False
    if "S11" in latest_data:
        # 10초 이내 갱신되었으면 연결된 것으로 간주
        if (now - latest_data["S11"].get("last_updated", 0)) < 10:
            nursery_connected = True
            
    return jsonify({
        "ok": True,
        "nursery_connected": nursery_connected,
        "uptime_seconds": int(uptime),
        "cpu_percent": psutil.cpu_percent(),
        "memory_percent": psutil.virtual_memory().percent
    })


@env_bp.route('/api/sensor/latest')
def get_latest_sensors():
    """각 노드별 최신 센서값 및 구동기 상태"""
    response_data = {}
    for node_id, data in latest_data.items():
        # sensor_controller.py의 latest_data 구조에 맞춰 모든 필드 포함
        response_data[node_id.lower()] = {
            "temperature": data.get("temp", 0),
            "humidity": data.get("humi", 0), # 'hum' -> 'humi' 키 일치화
            "light": data.get("light", 0),
            "water": data.get("water", 0),
            "led": data.get("led", "LED_OFF"),
            "pump": data.get("pump", "PUMP_OFF"),
            "fan": data.get("fan", "FAN_OFF"),
            "heater": data.get("heater", "HEATER_OFF"),
            "updated_at": data.get("last_seen", 0)
        }
    return jsonify({"ok": True, "sensors": response_data})


@env_bp.route('/api/sensor/control', methods=['POST'])
def control_sensor():
    """웹 GUI의 수동 제어 명령을 받아 ESP32에 반영 및 즉시 로깅"""
    data = request.get_json()
    node_id = data.get('node_id', '').lower()
    device = data.get('device')  # 'led', 'val', 'fan'
    state = data.get('state')    # 'ON', 'OFF'
    
    if not node_id or not device or not state:
        return jsonify({"ok": False, "error": "Invalid params"}), 400
        
    # --- 중앙 제어 핸들러를 통해 명령 실행 (상태 동기화, DB 기록, 패킷 전송 통합) ---
    from core.sensor_controller import execute_manual_control
    
    # state 문자열(ON/OFF)을 숫자 값으로 변환 (LED 100/0, 그 외 1/0)
    dev_lower = device.lower()
    state_upper = state.upper()
    state_val = 100 if state_upper == "ON" and dev_lower == "led" else (1 if state_upper == "ON" else 0)
    
    ok, msg = execute_manual_control(node_id, device, state_val, 2)
    
    if not ok:
        return jsonify({"ok": False, "error": msg}), 500
        
    return jsonify({"ok": True, "message": f"{node_id.upper()} {device.upper()} -> {state} 설정 및 로그 기록 완료"})


@env_bp.route('/api/logs/inout')
def get_inout_logs():
    """입출고 관련 로그 (A01, A04 노드 관련 운송 작업)"""
    from database.db_config import get_db_connection
    limit = request.args.get('limit', 20, type=int)
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT task_id, source_node, destination_node, task_status, ordered_at as time,
                       CASE WHEN source_node = 'a01' THEN '입고' ELSE '출고' END as type
                FROM transport_tasks 
                WHERE source_node IN ('a01', 'a04') OR destination_node IN ('a01', 'a04')
                ORDER BY task_id DESC LIMIT %s
            """, (limit,))
            rows = cursor.fetchall()
            for r in rows:
                if r['time']: r['time'] = r['time'].isoformat()
            return jsonify({"ok": True, "logs": rows})
    finally:
        conn.close()


@env_bp.route('/api/logs/nursery')
def get_nursery_logs():
    """육묘장 통합 로그 (센서 샘플 + 수동 제어)"""
    from database.db_config import get_db_connection
    limit = request.args.get('limit', 20, type=int)
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 수동 제어 + 센서 샘플을 통합하여 최신순 정렬
            # 간단하게 연산자 로그와 센서 평균 로그를 섞어서 출력
            cursor.execute("""
                SELECT * FROM (
                    (SELECT 'CONTROL' as type, logged_at as time, 
                            CONCAT(nc.node_id, ' ', CASE na.actuator_type_id WHEN 1 THEN '워터펌프' WHEN 2 THEN '팬' WHEN 3 THEN '온열히터' ELSE 'LED' END, ' ', state_value) as msg
                     FROM nursery_actuator_logs nal
                     JOIN nursery_actuators na ON nal.actuator_id = na.actuator_id
                     JOIN nursery_controllers nc ON na.controller_id = nc.controller_id
                     ORDER BY nal.log_id DESC LIMIT %s)
                    UNION ALL
                    (SELECT 'SENSOR' as type, measured_at as time,
                            CONCAT(nc.node_id, 
                                   MAX(CASE WHEN ns.sensor_type_id = 1 THEN CONCAT(' 온도:', value, '℃') ELSE '' END),
                                   MAX(CASE WHEN ns.sensor_type_id = 2 THEN CONCAT(' 습도:', value, CHAR(37)) ELSE '' END),
                                   MAX(CASE WHEN ns.sensor_type_id = 3 THEN CONCAT(' 광량:', value, 'lx') ELSE '' END)) as msg
                     FROM nursery_sensor_logs nsl
                     JOIN nursery_sensors ns ON nsl.sensor_id = ns.sensor_id
                     JOIN nursery_controllers nc ON ns.controller_id = nc.controller_id
                     GROUP BY nc.node_id, measured_at
                     ORDER BY measured_at DESC LIMIT %s)
                ) combined
                ORDER BY time DESC LIMIT %s
            """, (limit // 2, limit // 2, limit))
            rows = cursor.fetchall()
            for r in rows:
                if r['time']: r['time'] = r['time'].isoformat()
            return jsonify({"ok": True, "logs": rows})
    finally:
        conn.close()


@env_bp.route('/api/node/<node_id>/details')
def get_node_details(node_id):
    """노드의 상세 정보(품종, 입고일, 예정출고일)를 조회하는 API"""
    from database.db_config import get_db_connection
    from datetime import timedelta
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 1. 노드, 품종 및 작물 정보 조회
            cursor.execute("""
                SELECT fn.node_name, c.crop_name, sv.variety_name, sv.days_to_harvest
                FROM farm_nodes fn
                JOIN seedling_varieties sv ON fn.current_variety_id = sv.variety_id
                JOIN crops c ON sv.crop_id = c.crop_id
                WHERE fn.node_id = %s
            """, (node_id,))
            node_info = cursor.fetchone()
            
            if not node_info:
                return jsonify({"ok": False, "error": "Node not found"}), 404
            
            # 2. 가장 최근의 입고(운반 완료) 기록 조회 (입고 날짜)
            cursor.execute("""
                SELECT completed_at 
                FROM transport_tasks 
                WHERE destination_node = %s 
                  AND task_status = 2 
                ORDER BY completed_at DESC 
                LIMIT 1
            """, (node_id,))
            task_info = cursor.fetchone()
            
            incoming_date_str = "-"
            outgoing_date_str = "-"
            
            if task_info and task_info['completed_at']:
                incoming_date = task_info['completed_at']
                incoming_date_str = incoming_date.strftime('%Y-%m-%d')
                
                # 출고 예정일 = 입고일 + 수확 일수
                days = node_info['days_to_harvest'] or 0
                outgoing_date = incoming_date + timedelta(days=days)
                outgoing_date_str = outgoing_date.strftime('%Y-%m-%d')
            
            return jsonify({
                "ok": True,
                "node_id": node_id,
                "node_name": node_info['node_name'],
                "crop_name": node_info['crop_name'],
                "variety_name": node_info['variety_name'],
                "incoming_date": incoming_date_str,
                "outgoing_date": outgoing_date_str
            })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        conn.close()


@env_bp.route('/api/node/<node_id>/history')
def get_node_history(node_id):
    """노드의 최근 24시간 센서 이력을 조회하는 API"""
    from database.db_config import get_db_connection
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Temp=1, Humi=2, Light=3
            cursor.execute("""
                SELECT 
                    sl.measured_at,
                    MAX(CASE WHEN s.sensor_type_id = 1 THEN sl.value END) as temp,
                    MAX(CASE WHEN s.sensor_type_id = 2 THEN sl.value END) as humi,
                    MAX(CASE WHEN s.sensor_type_id = 3 THEN sl.value END) as light
                FROM nursery_sensors s
                JOIN nursery_sensor_logs sl ON s.sensor_id = sl.sensor_id
                JOIN nursery_controllers nc ON s.controller_id = nc.controller_id
                WHERE nc.node_id = %s
                AND sl.measured_at >= NOW() - INTERVAL 1 DAY
                GROUP BY sl.measured_at
                ORDER BY sl.measured_at ASC
            """, (node_id,))
            rows = cursor.fetchall()
            
            history = {
                "labels": [],
                "temp": [],
                "humi": [],
                "light": []
            }
            
            for r in rows:
                # ISO 포맷으로 시간 변환
                history["labels"].append(r['measured_at'].strftime('%H:%M'))
                history["temp"].append(float(r['temp']) if r['temp'] is not None else None)
                history["humi"].append(float(r['humi']) if r['humi'] is not None else None)
                history["light"].append(float(r['light']) if r['light'] is not None else None)
                
            return jsonify({
                "ok": True,
                "node_id": node_id,
                "history": history
            })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        conn.close()
