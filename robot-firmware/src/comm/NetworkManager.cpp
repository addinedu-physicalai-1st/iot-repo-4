/**
 * NetworkManager.cpp
 * ==================
 * ESP32 로봇 펌웨어용 네트워크 통신 매니저 구현 파일.
 * 
 * ArduinoJson 라이브러리를 사용하여 TCP/UDP JSON 통신을 처리한다.
 * 핸들러 내부의 비즈니스 로직(모터 구동, 센서 읽기 등)은 팀원이 구현할 것.
 */

#include "NetworkManager.h"

// ── 기본 포트 설정 ──
static const uint16_t DEFAULT_UDP_PORT = 9000;

// ============================================================
//  생성자 / 소멸자
// ============================================================

NetworkManager::NetworkManager()
    : _serverIP(nullptr)
    , _serverPort(0)
    , _udpPort(DEFAULT_UDP_PORT)
    , _motorController()
    , _lineFollower(_motorController)
{
    memset(_recvBuffer, 0, sizeof(_recvBuffer));
    Serial.println("[NetworkManager] 초기화 완료");
}

// ============================================================
//  하드웨어 초기화
// ============================================================

void NetworkManager::initHardware() {
    _motorController.init();
    Serial.println("[NetworkManager] 하드웨어 초기화 완료");
}

NetworkManager::~NetworkManager() {
    _tcpClient.stop();
    Serial.println("[NetworkManager] 소멸자 – 연결 해제");
}

// ============================================================
//  Wi-Fi 연결
// ============================================================

bool NetworkManager::connectWiFi(const char* ssid, const char* password) {
    Serial.printf("[NetworkManager] Wi-Fi 연결 시도: %s\n", ssid);

    WiFi.begin(ssid, password);

    // 최대 10초간 연결 대기
    int timeout = 20;  // 500ms × 20 = 10초
    while (WiFi.status() != WL_CONNECTED && timeout > 0) {
        delay(500);
        Serial.print(".");
        timeout--;
    }

    if (WiFi.status() == WL_CONNECTED) {
        Serial.printf("\n[NetworkManager] ✅ Wi-Fi 연결 성공! IP: %s\n",
                      WiFi.localIP().toString().c_str());
        return true;
    } else {
        Serial.println("\n[NetworkManager] ❌ Wi-Fi 연결 실패");
        return false;
    }
}

// ============================================================
//  서버 TCP 연결
// ============================================================

bool NetworkManager::connectToServer(const char* serverIP, uint16_t serverPort) {
    _serverIP = serverIP;
    _serverPort = serverPort;

    Serial.printf("[NetworkManager] 서버 TCP 연결 시도: %s:%d\n", serverIP, serverPort);

    if (_tcpClient.connect(serverIP, serverPort)) {
        Serial.println("[NetworkManager] ✅ 서버 연결 성공");
        return true;
    } else {
        Serial.println("[NetworkManager] ❌ 서버 연결 실패");
        return false;
    }
}

// ============================================================
//  메인 루프: TCP 수신 데이터 처리
// ============================================================

void NetworkManager::handleIncoming() {
    // 라인트레이싱 업데이트 (매 사이클 실행)
    _lineFollower.update();

    // TCP 소켓에 수신 데이터가 있는지 확인
    if (!_tcpClient.connected() || !_tcpClient.available()) {
        return;
    }

    // ── 수신 버퍼에 데이터 읽기 ──
    int len = _tcpClient.readBytesUntil('\n', _recvBuffer, sizeof(_recvBuffer) - 1);
    _recvBuffer[len] = '\0';

    String rawData = String(_recvBuffer);
    Serial.printf("[NetworkManager] 📨 수신: %s\n", rawData.c_str());

    // ── JSON 파싱 ──
    JsonDocument doc;
    if (!parseCommand(rawData, doc)) {
        sendResponse("FAIL", "JSON 파싱 실패");
        return;
    }

    // ── cmd 필드에 따라 핸들러 분기 ──
    const char* cmd = doc["cmd"];

    if (strcmp(cmd, "MOVE") == 0) {
        handleMove(doc);

    } else if (strcmp(cmd, "TASK") == 0) {
        handleTask(doc);

    } else if (strcmp(cmd, "MANUAL") == 0) {
        handleManual(doc);

    } else {
        Serial.printf("[NetworkManager] ⚠️ 알 수 없는 명령: %s\n", cmd);
        sendResponse("FAIL", "알 수 없는 명령");
    }
}

// ============================================================
//  JSON 파싱
// ============================================================

bool NetworkManager::parseCommand(const String& rawData, JsonDocument& doc) {
    DeserializationError error = deserializeJson(doc, rawData);

    if (error) {
        Serial.printf("[NetworkManager] ❌ JSON 파싱 오류: %s\n", error.c_str());
        return false;
    }

    return true;
}

// ============================================================
//  로봇 상태 UDP 브로드캐스트
// ============================================================

void NetworkManager::broadcastRobotState(const char* robotId, int posX, int posY, int battery) {
    /*
     * 서버에 로봇의 현재 상태를 UDP로 전송한다.
     *
     * 송신 포맷:
     *   {"type": "ROBOT_STATE", "robot_id": "R01", "pos_x": 120, "pos_y": 350, "battery": 80,
     *    "state": 1, "node": "A1", "sensors": [0,1,1,1,0]}
     */

    // 센서 값 조회
    int s1, s2, s3, s4, s5;
    _lineFollower.getSensorValues(s1, s2, s3, s4, s5);

    // JSON 문서 생성
    JsonDocument doc;
    doc["type"]     = "ROBOT_STATE";
    doc["robot_id"] = robotId;
    doc["pos_x"]    = posX;
    doc["pos_y"]    = posY;
    doc["battery"]  = battery;

    // 라인트레이싱 상태 추가
    doc["state"]    = static_cast<int>(_lineFollower.getState());
    doc["node"]     = _lineFollower.getCurrentNode();

    // 센서 배열 추가
    JsonArray sensors = doc["sensors"].to<JsonArray>();
    sensors.add(s1);
    sensors.add(s2);
    sensors.add(s3);
    sensors.add(s4);
    sensors.add(s5);

    // JSON → 문자열 직렬화
    char jsonBuffer[512];
    serializeJson(doc, jsonBuffer, sizeof(jsonBuffer));

    // UDP 패킷 전송
    _udpClient.beginPacket(_serverIP, _udpPort);
    _udpClient.print(jsonBuffer);
    _udpClient.endPacket();

    Serial.printf("[NetworkManager] 📡 상태 전송: %s\n", jsonBuffer);
}

// ============================================================
//  TCP 응답 전송
// ============================================================

void NetworkManager::sendResponse(const char* status, const char* msg) {
    /*
     * 서버에 명령 처리 결과를 TCP로 응답한다.
     *
     * 응답 포맷:
     *   {"status": "SUCCESS", "msg": "도착 완료"}
     */

    JsonDocument doc;
    doc["status"] = status;
    doc["msg"]    = msg;

    char jsonBuffer[256];
    serializeJson(doc, jsonBuffer, sizeof(jsonBuffer));

    _tcpClient.println(jsonBuffer);
    Serial.printf("[NetworkManager] 📤 응답 전송: %s\n", jsonBuffer);
}

// ============================================================
//  명령 핸들러 (뼈대 – 팀원이 내부 로직 구현)
// ============================================================

void NetworkManager::handleMove(JsonDocument& doc) {
    /*
     * 이동 명령 처리.
     *
     * 수신 포맷 1 (경로): {"cmd": "MOVE", "path": "12345"}
     *   - 1=L(좌회전), 2=R(우회전), 3=U(U턴), 4=S(직진), 5=E(종료)
     *   - 라인트레이싱으로 경로 추종 시작
     *
     * 수신 포맷 2 (노드): {"cmd": "MOVE", "target_node": "NODE-A1-001"}
     *   - 기존 방식 (미구현)
     */

    // 경로 기반 이동 (path 필드가 있는 경우)
    if (doc.containsKey("path")) {
        const char* path = doc["path"];
        Serial.printf("[NetworkManager] 🚗 경로 이동 명령 수신 → 경로: %s\n", path);

        _lineFollower.setPath(path);
        _lineFollower.start();

        sendResponse("SUCCESS", "경로 추종 시작");
        return;
    }

    // 노드 기반 이동 (target_node 필드가 있는 경우)
    if (doc.containsKey("target_node")) {
        const char* targetNode = doc["target_node"];
        Serial.printf("[NetworkManager] 🚗 노드 이동 명령 수신 → 목표: %s\n", targetNode);

        // TODO: 노드 좌표 조회 및 이동 로직 구현
        sendResponse("SUCCESS", "노드 이동 명령 수신 확인");
        return;
    }

    Serial.println("[NetworkManager] ⚠️ MOVE 명령에 path 또는 target_node 필드 없음");
    sendResponse("FAIL", "path 또는 target_node 필드 필요");
}

void NetworkManager::handleTask(JsonDocument& doc) {
    /*
     * 작업 명령 처리 (Pick-and-Place 등).
     * 수신: {"cmd": "TASK", "action": "PICK_AND_PLACE", "count": 5}
     *
     * TODO (팀원 구현):
     *   1) action, count 값 추출
     *   2) action이 "PICK_AND_PLACE"인 경우:
     *   3) 작업 완료 후 sendResponse() 호출
     */
    const char* action = doc["action"];
    int count = doc["count"] | 1;  // 기본값 1
    Serial.printf("[NetworkManager] 🎯 작업 명령 수신 → 동작: %s, 횟수: %d\n", action, count);

    // TODO: so-arm 제어 로직 구현
    // ArmController::pickAndPlace(count);

    sendResponse("SUCCESS", "작업 명령 수신 확인");
}

void NetworkManager::handleManual(JsonDocument& doc) {
    /*
     * 수동 제어 명령 처리.
     * 수신: {"cmd": "MANUAL", "device": "FAN", "state": "ON"}
     *
     * TODO (팀원 구현):
     *   1) device, state 값 추출
     *   2) device에 해당하는 GPIO 핀 번호 매핑
     *   3) state가 "ON"이면 HIGH, "OFF"이면 LOW로 핀 출력
     *   4) 제어 완료 후 sendResponse() 호출
     */
    const char* device = doc["device"];
    const char* state  = doc["state"];
    Serial.printf("[NetworkManager] 🔧 수동 제어 수신 → 장치: %s, 상태: %s\n", device, state);

    // TODO: GPIO 핀 제어 로직 구현
    // int pin = getPinForDevice(device);
    // digitalWrite(pin, strcmp(state, "ON") == 0 ? HIGH : LOW);

    sendResponse("SUCCESS", "수동 제어 수신 확인");
}
