import threading
import struct
import time
import sys
import select
import termios
import tty
import atexit
from network.tcp_robot_server import active_tcp_connections
from network.sfam_protocol import build_packet, MSG_ACTUATOR_CMD, ID_SERVER
from core import sensor_controller

# 터미널 복구를 위한 전역 변수
_ORIGINAL_TERMIOS = None
try:
    _ORIGINAL_TERMIOS = termios.tcgetattr(sys.stdin.fileno())
except:
    pass

def restore_terminal():
    """프로그램 종료 시 터미널 설정을 원래대로 복구하고 색상을 리셋합니다."""
    if _ORIGINAL_TERMIOS:
        fd = sys.stdin.fileno()
        termios.tcsetattr(fd, termios.TCSADRAIN, _ORIGINAL_TERMIOS)
    # ANSI 색상 및 속성 리셋
    sys.stdout.write("\033[0m")
    sys.stdout.flush()

# 프로그램 종료 시 무조건 실행되도록 등록
atexit.register(restore_terminal)

# 액추에이터 및 상태 매핑
ACTUATOR_MAP = {
    'MODE': 0, 'PUMP': 1, 'FAN': 2, 'HEATER': 3, 'LED': 4,
    '모드': 0, '워터펌프': 1, '팬': 2, '히터': 3, '조명': 4, 'LIGHT': 4,
    '온열히터': 3, '난방기': 3, '워터': 1, 'WATERPUMP': 1
}

STATE_MAP = {
    'ON': 1, 'OFF': 0, '켜짐': 1, '꺼짐': 0,
    '1': 1, '0': 0,
    'AUTO': 1, 'MANUAL': 0
}

def log_actuator_packet(node_id, act_id, state_val, trigger, raw_packet=None):
    """
    ESP32로 전송되는 액추에이터 패킷을 사람이 읽기 좋은 로그와 실제 바이너리 데이터를 함께 출력합니다.
    """
    act_names = {0: 'MODE(운영모드)', 1: 'PUMP(워터펌프)', 2: 'FAN(환기팬)', 3: 'HEATER(온열히터)', 4: 'LED(조명)'}
    name = act_names.get(act_id, f"ACT_{act_id}")
    
    # 상태 값 해석
    if act_id == 0: # MODE
        status_str = "AUTO(자동)" if state_val == 1 else "MANUAL(수동)"
    elif act_id == 4: # LED
        status_str = f"{state_val}%"
    else: # PUMP, FAN, HEATER
        status_str = "ON(켜짐)" if state_val == 1 else "OFF(꺼짐)"
        
    trigger_name = "수동(Manual)" if trigger == 2 else "자동(Auto)"
    
    # 바이너리 헥사 스트링 생성
    hex_data = raw_packet.hex(' ').upper() if raw_packet else "N/A"
    
    # [PACKET] 로그 출력 (Type 0x21: MSG_ACTUATOR_CMD)
    print(f"📦 [PKT 📤] {node_id} >> {name}:{status_str} ({trigger_name})")
    print(f"   └─ Raw Packet: {hex_data}")

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
    status_upper = status.upper()
    
    # LED 특수 처리 (숫자 우선)
    if target in ['LED', '조명', 'LIGHT']:
        try:
            val = int(status)
            if not (0 <= val <= 100):
                print(f"❌ LED 밝기 범위 초과 (0-100): {val}")
                return
        except ValueError:
            # 숫자가 아닌 경우 ON/OFF 유추
            if status_upper in ['ON', 'O', '1', '켜짐']: val = 100
            elif status_upper in ['OFF', 'F', '0', '꺼짐']: val = 0
    else:
        # 모든 장치 (PUMP, FAN, HEATER, MODE 등) 유추 확대
        if status_upper in ['ON', 'O', '1', '켜짐', 'TRUE', 'AUTO', '자동']: val = 1
        elif status_upper in ['OFF', 'F', '0', '꺼짐', 'FALSE', 'MANUAL', '수동']: val = 0
        else:
            try:
                val = int(status)
            except ValueError:
                pass

    if val is None:
        print(f"❌ 알 수 없는 상태: '{status}' (힌트: ON, OFF, 또는 숫자)")
        return
    
    # 4. 중앙 제어 핸들러를 통해 명령 실행
    ok, msg = sensor_controller.execute_manual_control(node_key, target, val, trigger=2, source="Terminal")
    
    if ok:
        print(f"✅ [CLI 명령 완료] {node_key} >> {target} {status_upper} (전송값:{val})")
    else:
        print(f"⚠️  [CLI 명령 실패] {node_key} >> {msg}")

def terminal_cli_loop():
    """실시간 키 입력을 감지하여 로그를 제어하는 루프"""
    if not _ORIGINAL_TERMIOS:
        return

    fd = sys.stdin.fileno()
    time.sleep(2)
    print("\n⌨️  [CLI] 커맨드 모드 가동 (':' 누르면 입력 가능)")
    
    while True:
        try:
            # 1. 한 글자씩 읽기 위해 터미널 모드 변경 (에코 꺼짐)
            tty.setcbreak(fd)
            # 입력이 들어올 때까지 0.5초 대기하면서 반복
            rlist, _, _ = select.select([sys.stdin], [], [], 0.5)
            
            if rlist:
                char = sys.stdin.read(1)
                if char == ':':
                    # 2. ':' 가 들어오는 순간 즉시 로그 차단
                    sensor_controller.log_suppressed = True
                    # 표준 입력 모드로 복구하여 input() 사용 준비
                    termios.tcsetattr(fd, termios.TCSADRAIN, _ORIGINAL_TERMIOS)
                    
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
            
            # 루프 끝에서 모드 복구 (안정성)
            termios.tcsetattr(fd, termios.TCSADRAIN, _ORIGINAL_TERMIOS)
            
        except Exception:
            sensor_controller.log_suppressed = False
            try:
                termios.tcsetattr(fd, termios.TCSADRAIN, _ORIGINAL_TERMIOS)
            except: pass
            time.sleep(1)


def start_terminal_cli():
    """CLI 핸들러 스레드 시작"""
    cli_thread = threading.Thread(target=terminal_cli_loop, daemon=True)
    cli_thread.start()
