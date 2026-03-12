"""
노드 식별 모듈
- ESP32 컨트롤러 ID를 기반으로 노드 ID와 제어기 ID를 할당합니다.
- 원본: integrated_server.py → identify_node()
"""
import re


def identify_node(raw_id):
    """
    ESP32에서 전송된 원시 ID를 파싱하여 (clean_id, node_id, controller_id) 튜플을 반환합니다.
    
    ID 매핑 규칙:
      - 1      → A01, CTRL-INBOUND-01     (입고장)
      - 99     → O99, CTRL-OUTBOUND-99    (출고장)
      - 17~19 (0x11~0x13) → S11~S13, CTRL-NURSERY-xx (센서 구역)
      - 33~35 (0x21~0x23) → R14~R16, CTRL-NURSERY-xx (재배 구역)
      - 기타   → nXX, CTRL-UNKNOWN-XX
    """
    try:
        clean_id = int(re.sub(r'[^0-9]', '', str(raw_id))) if re.sub(r'[^0-9]', '', str(raw_id)) else 0
    except:
        clean_id = 0

    if clean_id == 1:
        node_id, dyn_ctrl_id = "A01", "CTRL-INBOUND-01"
    elif clean_id == 99:
        node_id, dyn_ctrl_id = f"O{clean_id}", "CTRL-OUTBOUND-99"
    elif 17 <= clean_id <= 19:  # 0x11 ~ 0x13
        node_id, dyn_ctrl_id = f"S{clean_id-6}", f"CTRL-NURSERY-{clean_id-16:02d}"
    elif 33 <= clean_id <= 35:  # 0x21 ~ 0x23
        node_id, dyn_ctrl_id = f"R{clean_id-19}", f"CTRL-NURSERY-{clean_id-20:02d}"
    else:
        node_id, dyn_ctrl_id = f"n{clean_id}", f"CTRL-UNKNOWN-{clean_id}"

    return clean_id, node_id, dyn_ctrl_id
