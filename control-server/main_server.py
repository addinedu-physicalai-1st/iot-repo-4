"""
🌿 스마트팜 통합 중앙 제어 서버 (Entry Point)
- Flask 웹서버 + 로봇 TCP 서버 + ESP32-CAM UDP + 자동 작업 배차를 통합 실행합니다.
- 원본: integrated_server.py + server/app.py 통합

실행 방법:
    cd control-server
    python main_server.py
"""
import sys
import struct
import logging
import threading
import secrets

from flask import Flask, request, jsonify, render_template, redirect, url_for, session

# ─── Flask 앱 생성 ───
app = Flask(__name__)
# 세션을 위한 시크릿 키 설정 (시작할 때마다 임의 생성, 재시작 시 로그인 풀림)
app.secret_key = secrets.token_hex(16)

# 조용한 모드 (반복되는 HTTP 로그 숨김)
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)
print("🤫 [Quiet Mode] 조용한 모드로 서버를 시작합니다. (반복되는 HTTP 접속 로그 숨김)")

# ─── 모듈 import ───
from core.node_identifier import identify_node
from core.sensor_controller import process_sensor_and_control, latest_data, load_latest_sensor_data_from_db
from core.init_db import init_base_data
from network.tcp_robot_server import tcp_robot_server
from network.task_dispatcher import task_dispatcher_loop
from network.udp_camera_server import udp_camera_server
from network.terminal_cli import start_terminal_cli
from domain.rfid_handler import rfid_bp
from domain.robot_api import robot_bp
from domain.environment_api import env_bp
from domain.camera_api import camera_bp
from domain.auth_api import auth_bp

# ─── Blueprint 등록 ───
app.register_blueprint(rfid_bp)
app.register_blueprint(robot_bp)
app.register_blueprint(env_bp)
app.register_blueprint(camera_bp)
app.register_blueprint(auth_bp)


# =====================================================================
# 🔐 보안: 모든 라우트 앞에 로그인 강제 확인 (화이트리스트 제외)
# =====================================================================
@app.before_request
def require_login():
    # 정적 파일이나 인증 API, 외부 기기(센서) 전송용 API는 제외
    if request.path.startswith('/static/') or request.path.startswith('/api/') or \
       request.path in ['/login', '/logout', '/data', '/binary-data']:
        return None
    if not session.get('logged_in'):
        return redirect(url_for('auth.login'))

# =====================================================================
# 📡 센서 데이터 수신 API (JSON)
# =====================================================================
@app.route('/data', methods=['POST'])
def receive_data():
    content = request.get_json()
    if not content:
        return "No JSON data", 400
    p_id, node_id, dyn_ctrl_id = identify_node(
        content.get('controller_id') or content.get('node_id')
    )
    led, val, fan = process_sensor_and_control(
        p_id, node_id, dyn_ctrl_id,
        content.get('temperature', 0),
        content.get('humidity', 0),
        content.get('light', 0),
        content.get('water', 0)
    )
    return jsonify({"led": led, "val": val, "fan": fan}), 200


# =====================================================================
# 📡 센서 데이터 수신 API (Binary)
# =====================================================================
def calculate_crc16(data: bytes):
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if (crc & 0x0001) else crc >> 1
    return crc


@app.route('/binary-data', methods=['POST'])
def handle_binary_data():
    raw_data = request.get_data()
    if len(raw_data) != 15:
        return "Invalid Length", 400
    stx, c_id, count, _, temp_raw, hum, light, crc_rx, etx = struct.unpack("<BHHBhHHHB", raw_data)
    if calculate_crc16(raw_data[1:12]) != crc_rx:
        return "CRC Failed", 400

    p_id, node_id, dyn_ctrl_id = identify_node(c_id)
    # 기존 바이너리 규격에는 수위(water)가 없으므로 0 혹은 None 전달
    led, val, fan = process_sensor_and_control(p_id, node_id, dyn_ctrl_id, temp_raw / 10.0, hum, light, 0)
    return f"{led},{val},{fan}", 200


# =====================================================================
@app.route('/')
def index():
    if not session.get('logged_in'):
        return redirect(url_for('auth.login'))
    return render_template('index.html')


# =====================================================================
# 🚀 서버 실행
# =====================================================================
if __name__ == '__main__':
    flask_port = 5001
    
    print(f"🌿 Smart Farm 통합 서버가 시작됩니다. (Flask:{flask_port} / TCP:8000 / UDP:7070)")

    print("\n[INIT] DB 마스터 데이터 점검 중...")
    init_base_data()
    
    print("\n[INIT] 메모리 캐시 초기화 중...")
    load_latest_sensor_data_from_db()

    # 백그라운드 스레드 시작
    threading.Thread(target=tcp_robot_server, daemon=True).start()     # AGV TCP (포트 8000)
    threading.Thread(target=task_dispatcher_loop, daemon=True).start() # 자동 배차 (3초 주기)
    threading.Thread(target=udp_camera_server, daemon=True).start()    # ESP32-CAM UDP (포트 7070)
    start_terminal_cli()                                              # 인터랙티브 CLI 가동 (:)

    try:
        app.run(host='0.0.0.0', port=flask_port, debug=False, use_reloader=False)
    except KeyboardInterrupt:
        print("\n👋 서버를 종료합니다... (터미널 복구 중)")
    except OSError as e:
        print(f"\n❌ [Flask Server] 포트 {flask_port} 사용 불가: {e}")
        print(f"👉 터미널에서 'sudo kill -9 $(sudo lsof -t -i:{flask_port})' 명령어로 이전 프로세스를 종료해주세요.")
    finally:
        print("✅ 종료 완료.")
