"""
RFID 카드 인식 처리 모듈
- 작업자/화분 카드 인식 및 입출고 처리
- 원본: integrated_server.py → RFID 관련 라우트 핸들러
"""
import re
from datetime import datetime
from flask import Blueprint, request, jsonify
from database.db_config import get_db_connection

rfid_bp = Blueprint('rfid', __name__)

# ─── 전역 상태 (필요 시 확장용으로 남겨둠) ───
station_state = {"mode": "IDLE"}


@rfid_bp.route('/api/rfid', methods=['POST'])
def receive_rfid():
    content = request.get_json()
    uid = content.get('uid')

    if not uid:
        return jsonify({"status": "error", "message": "UID is missing"}), 400

    print(f"💳 [RFID 인식] 수신된 UID: {uid}")

    if uid in REGISTERED_USERS:
        user_info = REGISTERED_USERS[uid]
        print(f"✅ 인증 성공: {user_info['name']} ({user_info['role']})")
        return jsonify({"status": "success", "message": f"{user_info['name']}님 환영합니다."}), 200
    else:
        print(f"❌ 미등록 카드 접근 시도: {uid}")
        return jsonify({"status": "error", "message": "미등록 카드입니다."}), 403


@rfid_bp.route('/api/rfid_inoutbound', methods=['POST'])
def receive_rfid_inoutbound():
    """RFID 화분 인식을 통한 즉시 입고 처리 (마스터 카드 필요 없음)"""
    content = request.get_json()
    if not content:
        return jsonify({"status": "error", "message": "No JSON data"}), 400

    uid = content.get('uid')
    if not uid:
        return jsonify({"status": "error", "message": "UID is missing"}), 400

    # 공백 제거 및 대문자 변환
    uid = str(uid).replace(" ", "").upper()
    print(f"📦 [RFID 스캔] 화분(NFC:{uid}) 인식됨. 입고 처리 시도...")

    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # 1. 태그 UID로 트레이 정보 확인 (품종 및 작물명 포함)
            cursor.execute("""
                SELECT t.tray_id, t.variety_id, t.tray_status, v.variety_name, c.crop_name
                FROM trays t
                JOIN seedling_varieties v ON t.variety_id = v.variety_id
                JOIN crops c ON v.crop_id = c.crop_id
                WHERE t.nfc_uid = %s AND t.is_active = TRUE
            """, (uid,))
            tray_info = cursor.fetchone()

            if not tray_info:
                print(f"❌ [에러] NFC({uid})에 매핑된 활성 트레이가 없습니다.")
                return jsonify({"status": "error", "message": f"NFC({uid})에 매핑된 활성 트레이가 없습니다."}), 404
            
            # 2. 트레이 상태 확인 (이미 이동 중이거나 비어있으면 불가)
            if tray_info['tray_status'] in [2, 3, 4]:  # IN_TRANSIT, EMPTY, DAMAGED
                status_map = {2: "이동 중", 3: "비어 있음", 4: "파손"}
                msg = f"상태가 '{status_map.get(tray_info['tray_status'])}'인 트레이는 입고할 수 없습니다."
                print(f"⚠️ [경고] {msg}")
                return jsonify({"status": "error", "message": msg}), 400

            variety_id = tray_info['variety_id']

            # 3. 해당 품종(variety)을 보관할 수 있고 예약된 자리를 제외하고 빈자리가 있는 재배구역(node_type=1) 노드 탐색
            # UNSIGNED 컬럼 감산 시 오류 방지를 위해 CAST 사용
            cursor.execute("""
                SELECT fn.node_id, fn.node_name, 
                       (CAST(fn.max_capacity AS SIGNED) - CAST(fn.current_quantity AS SIGNED) - CAST(IFNULL(tt.reserved, 0) AS SIGNED)) as available_spots
                FROM farm_nodes fn
                LEFT JOIN (
                    SELECT destination_node, COUNT(*) as reserved 
                    FROM transport_tasks 
                    WHERE task_status IN (0, 1) 
                    GROUP BY destination_node
                ) tt ON fn.node_id = tt.destination_node
                WHERE fn.node_type_id = 1 
                  AND fn.current_variety_id = %s 
                  AND fn.is_active = TRUE
                  AND (CAST(fn.max_capacity AS SIGNED) - CAST(fn.current_quantity AS SIGNED) - CAST(IFNULL(tt.reserved, 0) AS SIGNED)) > 0
                ORDER BY available_spots DESC, fn.node_id ASC
                LIMIT 1
            """, (variety_id,))
            node_info = cursor.fetchone()

            if not node_info:
                print(f"⚠️ [경고] 품종 ID {variety_id}을 적재할 빈 재배구역이 없습니다!")
                return jsonify({"status": "error", "message": "해당 품종을 적재할 빈 재배구역이 없습니다!"}), 404

            target_node = node_info['node_id']
            source_node = 'A01' # 기본 출발지는 입고장

            # 4. 배차 지시 저장 (transport_tasks)
            # AGV ID는 현재 시스템에서 기본값으로 리팩토링 중이므로 R01 지정
            agv_id = 'R01'
            sql = """INSERT INTO transport_tasks 
                    (agv_id, variety_id, source_node, destination_node, ordered_by, quantity, task_status, ordered_at) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"""
            task_values = (agv_id, variety_id, source_node, target_node, 1, 1, 0, datetime.now())
            cursor.execute(sql, task_values)
            
            task_id = cursor.lastrowid
            
            # 5. 트레이 상태 IN_TRANSIT(2) 변경
            cursor.execute("UPDATE trays SET tray_status = 2 WHERE nfc_uid = %s", (uid,))

            # 6. 목적지 노드에 품종 정보 선제적 업데이트 (환경 제어 연동)
            # 입고 작업이 생성됨과 동시에 해당 구역의 환경 기준을 품종에 맞춰 조정합니다.
            cursor.execute("UPDATE farm_nodes SET current_variety_id = %s WHERE node_id = %s", (variety_id, target_node))

        conn.commit()
        variety_display = f"{tray_info['variety_name']}({tray_info['crop_name']})"
        print(f"🤖 [배차 완료] {source_node} → {node_info['node_name']}({target_node}) (Task ID: {task_id})")

        return jsonify({
            "status": "success", 
            "message": f"{variety_display} 입고 시작. 목적지: {node_info['node_name']}",
            "task_id": task_id
        }), 200

    except Exception as e:
        print(f"❌ [DB 에러] {e}")
        return jsonify({"status": "error", "message": f"DB 처리 중 오류 발생: {str(e)}"}), 500
    finally:
        if 'conn' in locals() and conn:
            conn.close()
