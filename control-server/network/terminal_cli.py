import threading
import struct
import time
import sys
import select
import termios
import tty
from network.tcp_robot_server import active_tcp_connections
from network.sfam_protocol import build_packet, MSG_ACTUATOR_CMD, ID_SERVER
from core import sensor_controller

# 액추에이터 및 상태 매핑
ACTUATOR_MAP = {
    'MODE': 0, 'PUMP': 1, 'FAN': 2, 'HEATER': 3, 'LED': 4,
    '모드': 0, '펌프': 1, '팬': 2, '히터': 3, '조명': 4, 'LIGHT': 4
}

STATE_MAP = {
    'ON': 1, 'OFF': 0, '켜짐': 1, '꺼짐': 0,
    '1': 1, '0': 0,
    'AUTO': 1, 'MANUAL': 0
}

def process_command(cmd_line):
    """명령어 파싱 및 패킷 전송 로직"""
    if not cmd_line.startswith(":"):
        return
        
    cmd_line = cmd_line[1:].strip()
    if not cmd_line:
        return
        
    parts = cmd_line.split()
    if len(parts) < 3:
        print("⚠️  형식 오류! 예: 'S13 LED 100' 또는 'S11 PUMP ON'")
        return
    
    node_key = parts[0].upper() # e.g., S11
    target = parts[1].upper()   # e.g., LED
    status = parts[2].upper()   # e.g., 100 or ON
    
    # 1. 대상 프로토콜 ID 계산
    target_protocol_id = 0
    if node_key.startswith('S'):
        try:
            num = int(node_key[1:])
            target_protocol_id = num + 6
        except:
            print(f"❌ 노드 번호 해석 실패: {node_key}")
            return
    else:
        print(f"❌ 지원되지 않는 노드 형식입니다: {node_key}")
        return
    
    # 2. 액추에이터 변환
    act_id = ACTUATOR_MAP.get(target)
    if act_id is None:
        print(f"❌ 알 수 없는 장치: {target}")
        return

    # 3. 상태 값 변환 (LED는 0-100, 그 외는 ON/OFF)
    val = None
    if target in ['LED', '조명', 'LIGHT']:
        try:
            val = int(status)
            if not (0 <= val <= 100): raise ValueError
        except:
            val = STATE_MAP.get(status)
            if val is not None: val = 100 if val == 1 else 0 # ON=100, OFF=0
    else:
        val = STATE_MAP.get(status)
        if val is None:
            try:
                val = int(status)
            except: pass

    if val is None:
        print(f"❌ 알 수 없는 상태: {status}")
        return
    
    # 4. 패킷 생성 및 전송
    # Payload: [actuator_id(1), state(1), trigger(1), duration(1)]
    payload = struct.pack('BBBB', act_id, val, 2, 0) # Trigger 2 = MANUAL
    packet = build_packet(MSG_ACTUATOR_CMD, ID_SERVER, target_protocol_id, 0, payload)
    
    if node_key in active_tcp_connections:
        try:
            active_tcp_connections[node_key].sendall(packet)
            print(f"✅ [명령 완료] {node_key} >> {target}(ID:{act_id}) {status}(Val:{val})")
            # 5. DB에 수동 제어 로그 저장
            sensor_controller.log_manual_actuator_to_db(node_key, act_id, val)
        except Exception as e:
            print(f"❌ [전송 실패] {e}")
    else:
        print(f"⚠️  [연결 없음] {node_key} 접속 상태 확인 필요")

def terminal_cli_loop():
    """실시간 키 입력을 감지하여 로그를 제어하는 루프"""
    fd = sys.stdin.fileno()
    time.sleep(2)
    print("\n⌨️  [CLI] 커맨드 모드 가동 (':' 누르면 입력 가능)")
    
    while True:
        old_settings = termios.tcgetattr(fd)
        try:
            # 1. 한 글자씩 읽기 위해 터미널 모드 변경 (Non-blocking 느낌으로)
            tty.setcbreak(fd)
            # 입력이 들어올 때까지 0.5초 대기하면서 반복
            rlist, _, _ = select.select([sys.stdin], [], [], 0.5)
            
            if rlist:
                char = sys.stdin.read(1)
                if char == ':':
                    # 2. ':' 가 들어오는 순간 즉시 로그 차단
                    sensor_controller.log_suppressed = True
                    # 표준 입력 모드로 복구하여 input() 사용 준비
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                    
                    # 화면 정리 및 입력 받기
                    sys.stdout.write("\r\033[K") # 현재 라인 지우기
                    cmd_body = input("🛠️ [커맨드 모드] 명령 입력 (예: S13 LED ON) >> :")
                    
                    # 3. 명령어 처리
                    process_command(":" + cmd_body)
                    
                    # 4. 잠시 대기 후 로그 복구
                    time.sleep(0.5)
                    sensor_controller.log_suppressed = False
                    sys.stdout.write("\n")
                else:
                    # ':' 외의 키는 그냥 무시하고 넘김
                    pass
        except Exception as e:
            sensor_controller.log_suppressed = False
            # termios 복구 시도
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            time.sleep(1)
        finally:
            # 루프 끝에서 항상 모드 복구 시도 (안정성)
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def start_terminal_cli():
    """CLI 핸들러 스레드 시작"""
    cli_thread = threading.Thread(target=terminal_cli_loop, daemon=True)
    cli_thread.start()
