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
 */

#include "src/comm/NetworkManager.h"

// ============================================================
//  설정값 (필요에 따라 수정)
// ============================================================

// Wi-Fi 설정
const char* WIFI_SSID     = "609-801";
const char* WIFI_PASSWORD = "01082065573";

// 중앙 서버 설정
const char* SERVER_IP   = "192.168.0.100";  // 서버 IP 주소
const uint16_t SERVER_PORT = 8080;          // 서버 TCP 포트

// 로봇 식별자
const char* ROBOT_ID = "R01";

// 상태 브로드캐스트 주기 (밀리초)
const unsigned long BROADCAST_INTERVAL = 500;

// ============================================================
//  전역 객체
// ============================================================

NetworkManager networkManager;

unsigned long lastBroadcastTime = 0;

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
    networkManager.initHardware();

    // 2. Wi-Fi 연결
    Serial.println("\n[Main] Wi-Fi 연결 중...");
    if (!networkManager.connectWiFi(WIFI_SSID, WIFI_PASSWORD)) {
        Serial.println("[Main] ❌ Wi-Fi 연결 실패! 5초 후 재시작합니다.");
        delay(5000);
        ESP.restart();
    }

    // 3. 서버 TCP 연결
    Serial.println("\n[Main] 서버 연결 중...");
    if (!networkManager.connectToServer(SERVER_IP, SERVER_PORT)) {
        Serial.println("[Main] ⚠️ 서버 연결 실패. 독립 모드로 동작합니다.");
    }

    Serial.println("\n========================================");
    Serial.println("   ✅ 초기화 완료 - 대기 중");
    Serial.println("========================================\n");
}

// ============================================================
//  loop()
// ============================================================

void loop() {
    // TCP 명령 수신 및 라인트레이싱 업데이트
    networkManager.handleIncoming();

    // 주기적 상태 브로드캐스트
    unsigned long currentTime = millis();
    if (currentTime - lastBroadcastTime >= BROADCAST_INTERVAL) {
        // 위치 좌표는 추후 구현 (현재 0, 0 전송)
        // 배터리 잔량도 추후 구현 (현재 100% 전송)
        networkManager.broadcastRobotState(ROBOT_ID, 0, 0, 100);
        lastBroadcastTime = currentTime;
    }
}
