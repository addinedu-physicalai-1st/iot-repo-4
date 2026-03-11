"""
로봇 제어 API 모듈
- 개별 로봇 제어, 비상 정지, GOTO/MOVE 명령 전송
- 원본: server/app.py + integrated_server.py 통합
"""
import json
from flask import Blueprint, request, jsonify
from network.tcp_robot_server import active_tcp_connections

robot_bp = Blueprint('robot', __name__)

# 로봇이 인식 가능한 목적지 노드 목록 (PathFinder 기준)
VALID_NODES = [
    "a01", "a02", "a03", "a04",
    "s05", "s06", "s07",
    "r08", "r09", "r10",
    "s11", "s12", "s13",
    "r14", "r15", "r16",
]


def send_to_robot(robot_id, cmd):
    """로봇에게 JSON 명령 전송. 성공 시 True 반환."""
    payload = json.dumps(cmd) + "\n"
    if robot_id and robot_id in active_tcp_connections:
        sock = active_tcp_connections[robot_id]
    elif active_tcp_connections:
        robot_id = next(iter(active_tcp_connections.keys()))
        sock = active_tcp_connections[robot_id]
    else:
        return False

    try:
        sock.sendall(payload.encode("utf-8"))
        print(f"📤 [TCP 전송] {robot_id} → {cmd}")
        return True
    except Exception as e:
        print(f"❌ [TCP 전송 실패] {robot_id}: {e}")
        if robot_id in active_tcp_connections:
            del active_tcp_connections[robot_id]
        return False


@robot_bp.route('/api/robot/control', methods=['POST'])
def control_robot():
    """개별 로봇 제어 (이동/정지)"""
    data = request.get_json()
    robot_id = data.get('robot_id')
    command = data.get('command')
    print(f"💻 [API 수신] 로봇: {robot_id} | 명령: {command}")
    return jsonify({"success": True, "message": f"{robot_id} 로봇 {command} 명령 처리 성공"})


@robot_bp.route('/api/robot/emergency_stop', methods=['POST'])
def emergency_stop():
    """전체 로봇 비상 정지"""
    print("🚨 [API 수신] 모든 로봇 비상 정지 명령 수신!")
    for rid in list(active_tcp_connections.keys()):
        send_to_robot(rid, {"cmd": "STOP"})
    return jsonify({"success": True, "message": "비상 정지 명령 처리 성공"})

@robot_bp.route('/api/robot/cmd', methods=['POST'])
def manual_control_cmd():
    """수동 이동 명령 전송 (W,A,S,D 조이스틱)"""
    data = request.get_json()
    robot_id = data.get('robot_id', 'R01')
    command = data.get('command', 'MOVE')
    direction = data.get('direction', 'STOP')
    
    cmd_dict = {"cmd": command, "direction": direction}
    if send_to_robot(robot_id, cmd_dict):
        return jsonify({"ok": True, "message": f"{direction} 이동 명령 전송"})
    return jsonify({"ok": False, "error": "로봇 연결 안됨"}), 503


@robot_bp.route('/api/robots')
def list_robots():
    """연결된 로봇 목록"""
    robots = list(active_tcp_connections.keys())
    return jsonify({"ok": True, "robots": robots})


@robot_bp.route('/api/tasks', methods=['GET', 'POST'])
def handle_tasks():
    """작업 조회 및 생성"""
    from database.db_config import get_db_connection
    from datetime import datetime

    if request.method == 'GET':
        limit = request.args.get('limit', 20, type=int)
        conn = None
        try:
            conn = get_db_connection()
            with conn.cursor() as cursor:
                # 최근 작업 내역 최신순으로 가져오기
                cursor.execute(
                    "SELECT task_id, agv_id as robot_id, destination_node, task_status, ordered_at as created_at "
                    "FROM transport_tasks ORDER BY task_id DESC LIMIT %s", 
                    (limit,)
                )
                tasks = cursor.fetchall()
                # datetime 객체를 문자열로 변환 ('2026-03-11T14:30:00' 포맷)
                for t in tasks:
                    if isinstance(t.get('created_at'), datetime):
                        t['created_at'] = t['created_at'].isoformat()
            
            return jsonify({"ok": True, "tasks": tasks})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
        finally:
            if conn:
                conn.close()

    # POST (작업 생성) 처리
    data = request.get_json() or request.form
    destination = (data.get("destination") or "").strip().lower()
    req_robot_id = (data.get("robot_id") or "").strip()

    if not destination:
        return jsonify({"ok": False, "error": "목적지를 입력하세요"}), 400

    if destination not in VALID_NODES:
        return jsonify({"ok": False, "error": f"유효하지 않은 목적지: {destination}"}), 400

    # 연결된 로봇 확인 및 동적 할당
    agv_keys = [k for k in active_tcp_connections.keys() if k.startswith("R")]
    
    if req_robot_id:
        if req_robot_id not in agv_keys:
            return jsonify({"ok": False, "error": f"요청하신 로봇 '{req_robot_id}'이(가) 연결되어 있지 않습니다."}), 404
        robot_id = req_robot_id
    else:
        if not agv_keys:
            return jsonify({"ok": False, "error": "현재 사용 가능한 로봇이 서버에 연결되어 있지 않습니다."}), 503
        robot_id = sorted(agv_keys)[0]  # 첫 번째로 연결된 로봇 사용

    # MySQL transport_tasks에 저장
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("INSERT IGNORE INTO agv_robots (agv_id, status_id) VALUES (%s, 1)", (robot_id,))
            cursor.execute("INSERT IGNORE INTO farm_nodes (node_id, node_name, node_type_id, current_variety_id) VALUES ('a01', 'A01 (입고장)', 2, 1)")
            cursor.execute("INSERT IGNORE INTO farm_nodes (node_id, node_name, node_type_id, current_variety_id) VALUES (%s, %s, 2, 1)", (destination, destination))

            sql = """INSERT INTO transport_tasks 
                    (agv_id, variety_id, source_node, destination_node, ordered_by, quantity, task_status, ordered_at) 
                    VALUES (%s, 1, %s, %s, 1, 1, 0, %s)"""
            cursor.execute(sql, (robot_id, 'a01', destination, datetime.now()))
            task_id = cursor.lastrowid
        conn.commit()
    except Exception as e:
        print(f"❌ DB 작업 저장 에러: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()

    # GOTO 명령 전송
    cmd = {"cmd": "GOTO", "target_node": destination}
    if send_to_robot(robot_id, cmd):
        return jsonify({"ok": True, "task_id": task_id, "message": f"목적지 {destination}로 전송 완료"})
    else:
        return jsonify({"ok": False, "error": "연결된 로봇이 없습니다.", "task_id": task_id}), 503


@robot_bp.route('/api/send_path', methods=['POST'])
def send_path():
    """경로 직접 전송 (MOVE + path)"""
    data = request.get_json() or request.form
    path = (data.get("path") or "").strip().upper()
    robot_id = (data.get("robot_id") or "R01").strip() or None

    if not path:
        return jsonify({"ok": False, "error": "경로를 입력하세요. (예: SE, LRS)"}), 400

    cmd = {"cmd": "MOVE", "path": path}
    if send_to_robot(robot_id, cmd):
        return jsonify({"ok": True, "message": f"경로 '{path}' 전송 완료"})
    return jsonify({"ok": False, "error": "연결된 로봇이 없습니다."}), 503

@robot_bp.route('/api/robot_state')
def get_robot_state():
    """웹 대시보드(AGV 아이콘 이동)를 위한 현재 로봇 상태 반환"""
    from network.tcp_robot_server import active_tcp_connections, latest_robot_state
    
    robot_id = request.args.get('robot_id')
    
    if not robot_id:
        active_r = [k for k in latest_robot_state.keys() if k.startswith('R')]
        robot_id = active_r[0] if active_r else "R01"
    
    if robot_id in latest_robot_state:
        state_data = latest_robot_state[robot_id].copy()
        state_data['robot_id'] = robot_id  # Frontend에서 참조할 수 있게 주입
        
        return jsonify({
            "ok": True, 
            "connected": robot_id in active_tcp_connections,
            "state": state_data
        })
        
    return jsonify({"ok": False, "error": "데이터 없음"}), 404
