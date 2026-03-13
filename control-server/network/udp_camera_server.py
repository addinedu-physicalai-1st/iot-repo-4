"""
ESP32-CAM UDP 영상 수신 서버
- 포트 7070에서 ESP32-CAM의 UDP JPEG 패킷을 수신하여 프레임을 조립합니다.
- 원본: server/app.py → camera_udp_receiver_thread()
"""
import socket
import threading
import time
from datetime import datetime
from core.node_identifier import identify_node

# 전역 상태 - 카메라 ID별로 프레임 관리
latest_camera_frames = {}          # {camera_id: bytes}
_camera_frame_locks = {}           # {camera_id: Lock}
_camera_frame_events = {}          # {camera_id: Event}
camera_fps = {}                    # {camera_id: float}
_camera_last_updates = {}          # {camera_id: float} (마지막 풀 프레임 수신 시각)
_camera_last_activity = {}         # {camera_id: float} (마지막 패킷 수신 시각)

# 최소 1x1 회색 JPEG (카메라 미연결 시 placeholder)
PLACEHOLDER_JPEG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f"
    b"\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00?\x00\xb8\xe0\x7f\xff\xd9"
)


def _ensure_camera(camera_id):
    """카메라 ID별 상태 초기화 및 접속 로그 출력 (장기간 미수신 후 재수신 시 로그 표시)"""
    now_t = time.time()
    
    # 1. 신규 접속 처리 (메모리에 없는 경우)
    if camera_id not in _camera_frame_locks:
        _camera_frame_locks[camera_id] = threading.Lock()
        _camera_frame_events[camera_id] = threading.Event()
        camera_fps[camera_id] = 0.0
        _camera_last_updates[camera_id] = 0.0
        _camera_last_activity[camera_id] = now_t
        latest_camera_frames[camera_id] = None

        _, node_id, _ = identify_node(camera_id)
        zone_info = f" ({node_id} 구역)" if node_id.startswith('S') or node_id in ['I10', 'O99'] else ""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] 📷 [UDP Camera] 새 카메라 접속 확인: ID {camera_id}{zone_info}")
    
    # 2. 재접속 처리 (10초 이상 끊겼다가 다시 들어온 경우)
    else:
        last_activity = _camera_last_activity.get(camera_id, 0)
        if (now_t - last_activity) > 10.0:
            _, node_id, _ = identify_node(camera_id)
            zone_info = f" ({node_id} 구역)" if node_id.startswith('S') or node_id in ['I10', 'O99'] else ""
            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"[{timestamp}] 📷 [UDP Camera] 카메라 재접속 감지: ID {camera_id}{zone_info}")
        
        # 패킷 수신 시각 갱신
        _camera_last_activity[camera_id] = now_t


def get_camera_frame(camera_id):
    """특정 카메라의 최신 프레임 반환 (없으면 placeholder)"""
    _ensure_camera(camera_id)
    with _camera_frame_locks[camera_id]:
        return latest_camera_frames.get(camera_id) or PLACEHOLDER_JPEG


def wait_for_frame(camera_id, timeout=2.0):
    """새 프레임이 올 때까지 대기"""
    _ensure_camera(camera_id)
    return _camera_frame_events[camera_id].wait(timeout=timeout)


def clear_frame_event(camera_id):
    """프레임 이벤트 플래그 초기화"""
    if camera_id in _camera_frame_events:
        _camera_frame_events[camera_id].clear()


def udp_camera_server(port=7070):
    """ESP32-CAM UDP 패킷 수신·조립 (메인 루프) - 카메라 ID별 분리 처리"""

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
    sock.settimeout(1.0)
    try:
        sock.bind(("0.0.0.0", port))
    except OSError as e:
        print(f"❌ [UDP] 포트 {port} 바인드 실패: {e}")
        return
    print(f"\n📷 [UDP Camera] ESP32-CAM 수신 대기 중... (포트 {port})")

    frames = {}
    last_frame_no = {}

    while True:
        try:
            data, _ = sock.recvfrom(2048)
            if len(data) < 5:
                continue

            camera_id = data[0]       # Byte 0 = vehicle/camera ID
            f_no = data[1]
            p_no = data[2]
            received_checksum = data[3]
            chunk = data[4:]

            _ensure_camera(camera_id)

            if camera_id not in last_frame_no:
                last_frame_no[camera_id] = -1
            lfn = last_frame_no[camera_id]
            if f_no < lfn and (lfn - f_no) < 200:
                continue

            if camera_id not in frames:
                frames[camera_id] = {}
            vframes = frames[camera_id]

            if f_no not in vframes:
                if len(vframes) > 3:
                    del vframes[min(vframes.keys())]
                vframes[f_no] = {"chunks": {}, "target_checksum": 0}
            vframes[f_no]["chunks"][p_no] = chunk

            if chunk.find(b"\xff\xd9") != -1:
                vframes[f_no]["target_checksum"] = received_checksum
                indices = sorted(vframes[f_no]["chunks"].keys())

                if indices and indices[0] == 0 and len(indices) == indices[-1] + 1:
                    full_data = b"".join([vframes[f_no]["chunks"][i] for i in indices])
                    calculated_checksum = sum(full_data) % 256

                    if calculated_checksum == vframes[f_no]["target_checksum"]:
                        with _camera_frame_locks[camera_id]:
                            latest_camera_frames[camera_id] = full_data
                        _camera_frame_events[camera_id].set()
                        now_t = time.time()
                        prev = _camera_last_updates.get(camera_id, 0)
                        if prev > 0:
                            camera_fps[camera_id] = 1.0 / (now_t - prev)
                        _camera_last_updates[camera_id] = now_t
                        last_frame_no[camera_id] = f_no

                frames[camera_id] = {k: v for k, v in vframes.items() if k > f_no}
        except socket.timeout:
            continue
        except Exception as e:
            print(f"❌ [UDP] 수신 오류: {e}")
            time.sleep(0.5)
