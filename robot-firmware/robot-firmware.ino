/**
 * robot-firmware.ino
 * ==================
 * ESP32 스마트팜 로봇 메인 스케치 파일.
 *
 * 기능:
 *   - Wi-Fi 연결 및 서버 통신
 *   - TCP 명령 수신 (MOVE, TASK, MANUAL)
 *   - 라인트레이싱 경로 추종
 *   - UDP 상태 브로드캐스트
 *
 * Wi-Fi / 서버 설정은 아래 #define에서 수동 수정
 */

// Wi-Fi / 서버 설정 (수동 수정)
#define WIFI_SSID     "addinedu_201class_4-2.4G"
#define WIFI_PASSWORD "201class4!"
#define SERVER_IP     "192.168.0.17"
#define SERVER_TCP_PORT 8080
#define SERVER_UDP_PORT 7070

#include <WiFi.h>
#include "src/comm/RobotNetworkManager.h"

// ============================================================
//  설정값
// ============================================================

// 로봇 식별자
const char* ROBOT_ID = "R01";

// 상태 브로드캐스트 주기 (밀리초)
const unsigned long BROADCAST_INTERVAL = 1000; // 1초

// ============================================================
//  전역 객체
// ============================================================

RobotNetworkManager robotNetworkManager;

unsigned long lastBroadcastTime = 0;

// 시리얼 버퍼
String serialBuffer;

// ============================================================
//  setup()
// ============================================================

void setup() {
    Serial.begin(115200);
    delay(1000);

    Serial.println();
    Serial.println("========================================");
    Serial.println("   🤖 스마트팜 로봇 펌웨어 시작");
    Serial.println("========================================");

    // 1. 하드웨어 초기화 (모터, 센서)
    robotNetworkManager.initHardware();

    // 2. Wi-Fi 연결
    Serial.println("\n[Main] Wi-Fi 연결 중...");
    if (!robotNetworkManager.connectWiFi(WIFI_SSID, WIFI_PASSWORD)) {
        Serial.println("[Main] ❌ Wi-Fi 연결 실패! 5초 후 재시작합니다.");
        delay(5000);
        ESP.restart();
    }

    // 3. 서버 TCP 연결
    Serial.println("\n[Main] 서버 연결 중...");
    if (!robotNetworkManager.connectToServer(SERVER_IP, SERVER_TCP_PORT)) {
        Serial.println("[Main] ⚠️ 서버 연결 실패. 독립 모드로 동작합니다.");
    }

    Serial.println("\n========================================");
    Serial.println("   ✅ 초기화 완료 - 대기 중");
    Serial.println("   [안내] 전원 켠 직후 또는 물리적으로 옮긴 뒤에는");
    Serial.println("          서버에서 SET_LOC으로 초기 위치를 설정하세요.");
    Serial.println("========================================\n");
}

// ============================================================
//  loop()
// ============================================================

void loop() {
    // 시리얼을 통한 수동 위치 설정 명령 처리
    while (Serial.available() > 0) {
        char c = static_cast<char>(Serial.read());
        if (c == '\n' || c == '\r') {
            if (serialBuffer.length() > 0) {
                // 예: SETLOC s06 N
                Serial.printf("[Main] 시리얼 명령 수신: %s\n", serialBuffer.c_str());
                int firstSpace = serialBuffer.indexOf(' ');
                if (firstSpace > 0) {
                    String cmd = serialBuffer.substring(0, firstSpace);
                    cmd.trim();
                    if (cmd.equalsIgnoreCase("SETLOC")) {
                        String rest = serialBuffer.substring(firstSpace + 1);
                        rest.trim();
                        int secondSpace = rest.indexOf(' ');
                        String nodeStr;
                        String dirStr;
                        if (secondSpace > 0) {
                            nodeStr = rest.substring(0, secondSpace);
                            dirStr = rest.substring(secondSpace + 1);
                        } else {
                            nodeStr = rest;
                        }
                        nodeStr.trim();
                        dirStr.trim();

                        if (nodeStr.length() == 0 || dirStr.length() == 0) {
                            Serial.println("[Main] SETLOC 사용법: SETLOC s06 N");
                        } else {
                            char dirChar = dirStr.charAt(0);
                            int dirCode = -1;
                            switch (toupper(dirChar)) {
                                case 'N': dirCode = 0; break;
                                case 'E': dirCode = 1; break;
                                case 'S': dirCode = 2; break;
                                case 'W': dirCode = 3; break;
                                default: break;
                            }
                            if (dirCode < 0) {
                                Serial.println("[Main] 방향은 N/E/S/W 중 하나여야 합니다.");
                            } else {
                                if (robotNetworkManager.setLocationByNodeName(nodeStr.c_str(), dirCode)) {
                                    Serial.printf("[Main] 위치 수동 설정 완료: %s %c\n",
                                                  nodeStr.c_str(), toupper(dirChar));
                                } else {
                                    Serial.println("[Main] 위치 수동 설정 실패: 노드 이름을 확인하세요.");
                                }
                            }
                        }
                    }
                }
                serialBuffer = "";
            }
        } else {
            serialBuffer += c;
        }
    }

    // TCP 명령 수신 및 라인트레이싱 업데이트
    robotNetworkManager.handleIncoming();

    // 주기적 상태 브로드캐스트 및 적외선 센서 시리얼 출력
    unsigned long currentTime = millis();
    if (currentTime - lastBroadcastTime >= BROADCAST_INTERVAL) {
        // WiFi 상태 시리얼 출력
        if (WiFi.status() == WL_CONNECTED) {
            Serial.printf("[WiFi] 연결됨 %s (RSSI: %ddBm)\n",
                          WiFi.localIP().toString().c_str(), WiFi.RSSI());
        } else {
            Serial.println("[WiFi] 끊김 - 재연결 대기");
        }

        // 적외선 센서 값 시리얼 출력 (S1~S5, 0=라인 없음, 1=라인 감지)
        int s1, s2, s3, s4, s5;
        robotNetworkManager.getLineFollower().getSensorValues(s1, s2, s3, s4, s5);
        Serial.printf("[IR] S1=%d S2=%d S3=%d S4=%d S5=%d\n", s1, s2, s3, s4, s5);

        // 위치 좌표는 추후 구현 (현재 0, 0 전송)
        // 배터리 잔량도 추후 구현 (현재 100% 전송)
        robotNetworkManager.broadcastRobotState(ROBOT_ID, 0, 0, 100);
        lastBroadcastTime = currentTime;
    }
}
