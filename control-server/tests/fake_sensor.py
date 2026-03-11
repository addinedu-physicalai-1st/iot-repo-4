"""
가상 육묘 센서 (TCP 8000 바이너리 통신)
- 3초마다 온도, 습도, 조도 데이터를 SFAM 바이너리 패킷으로 전송합니다.
"""
import socket
import time
import random
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from network.sfam_protocol import build_packet, MSG_SENSOR_BATCH, ID_SERVER

TCP_IP = "127.0.0.1"
TCP_PORT = 8000
NODE_ID = 0x11 # S11

def run_fake_sensor():
    print(f"🌱 [가상 센서] {TCP_IP}:{TCP_PORT} 접속 시도...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((TCP_IP, TCP_PORT))
        print("✅ 센서 연결 성공!")
        
        seq = 0
        while True:
            t = round(random.uniform(20.0, 30.0), 1)
            h = round(random.uniform(40.0, 70.0), 1)
            l = random.randint(100, 1000)
            
            pay = bytearray()
            pay.append(3) # sensor count
            
            # temp
            t_val = int(t * 100)
            pay.append(0x01)
            pay.append((t_val >> 16) & 0xFF)
            pay.append((t_val >> 8) & 0xFF)
            pay.append(t_val & 0xFF)
            
            # hum
            h_val = int(h * 100)
            pay.append(0x02)
            pay.append((h_val >> 16) & 0xFF)
            pay.append((h_val >> 8) & 0xFF)
            pay.append(h_val & 0xFF)
            
            # light
            l_val = int(l * 100)
            pay.append(0x03)
            pay.append((l_val >> 16) & 0xFF)
            pay.append((l_val >> 8) & 0xFF)
            pay.append(l_val & 0xFF)
            
            packet = build_packet(MSG_SENSOR_BATCH, NODE_ID, ID_SERVER, seq, bytes(pay))
            
            sock.sendall(packet)
            print(f"📤 [센서 전송] 온도:{t} 습도:{h} 조도:{l} | 패킷: {packet.hex()}")
            
            seq = (seq + 1) % 256
            time.sleep(3)
            
    except Exception as e:
        print(f"❌ 접속 실패: {e}")
    finally:
        sock.close()

if __name__ == "__main__":
    run_fake_sensor()
