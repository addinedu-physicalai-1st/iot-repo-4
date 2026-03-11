"""
서버 환경 모니터링 API
- 통합 프론트엔드 대시보드(SPA)와 통신하기 위한 JSON API 제공
"""
import psutil
import time
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
    """각 노드별 최신 온습도, 조도 센서값"""
    # JS에서 받아서 카드를 채우도록 포맷 변경
    response_data = {}
    for node_id, data in latest_data.items():
        response_data[node_id.lower()] = {
            "temperature": data.get("temp", 0),
            "humidity": data.get("humi", 0),
            "light": data.get("light", 0),
            "updated_at": data.get("last_updated", 0)
        }
    return jsonify({"ok": True, "sensors": response_data})


@env_bp.route('/api/sensor/control', methods=['POST'])
def control_sensor():
    """웹 GUI의 수동 제어 명령을 받아 ESP32에 반영"""
    data = request.get_json()
    node_id = data.get('node_id', '').lower()
    device = data.get('device')  # 'led', 'val', 'fan'
    state = data.get('state')    # 'ON', 'OFF'
    
    if not node_id or not device or not state:
        return jsonify({"ok": False, "error": "Invalid params"}), 400
        
    if node_id not in manual_overrides:
        manual_overrides[node_id] = {}
        
    cmd = f"{device.upper()}_{state.upper()}"
    manual_overrides[node_id][device.lower()] = cmd
    
    return jsonify({"ok": True, "message": f"{node_id.upper()} {device.upper()} -> {state} 설정 완료"})
