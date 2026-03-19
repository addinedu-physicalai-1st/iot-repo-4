/**
 * RobotNetworkManager.cpp
 * =======================
 * ESP32 로봇 펌웨어용 네트워크 통신 매니저 구현 파일.
 *
 * ArduinoJson 라이브러리를 사용하여 TCP/UDP JSON 통신을 처리한다.
 * 핸들러 내부의 비즈니스 로직(모터 구동, 센서 읽기 등)은 팀원이 구현할 것.
 * [수정됨] ESP32 기본 라이브러리 충돌을 막기 위해
 * 클래스 이름이 RobotNetworkManager로 변경되었습니다.
 */

#include "RobotNetworkManager.h"

// ── 기본 포트 설정 ──
static const uint16_t DEFAULT_UDP_PORT = 9000;

// ============================================================
//  생성자 / 소멸자
// ============================================================

RobotNetworkManager::RobotNetworkManager()
    : _serverIP(nullptr), _serverPort(0), _udpPort(DEFAULT_UDP_PORT),
      _msgCount(0), _lastReconnectAttempt(0), _lastHeartbeatMs(0), _sfamSeq(0),
      _rxSfamCount(0), _rxSfamPayLen(0), _motorController(), _armController(),
      _lineFollower(_motorController, _armController) {

  memset(_recvBuffer, 0, sizeof(_recvBuffer));
  memset(_rxSfamBuf, 0, sizeof(_rxSfamBuf));
  Serial.println("[RobotNetworkManager] 초기화 완료");
}

// ============================================================
//  하드웨어 초기화
// ============================================================

void RobotNetworkManager::initHardware() {
  _motorController.init();
  _lineFollower.stop();
  _rfidReader.init();
  _armController.init();
  _pathFinder.initGraph();
  Serial.println("[RobotNetworkManager] 하드웨어 초기화 완료");
}

void RobotNetworkManager::setArmEnabled(bool enabled) {
  _armController.setArmEnabled(enabled);
}

RobotNetworkManager::~RobotNetworkManager() {
  _tcpClient.stop();
  Serial.println("[RobotNetworkManager] 소멸자 – 연결 해제");
}

// ============================================================
//  Wi-Fi 연결
// ============================================================

bool RobotNetworkManager::connectWiFi(const char *ssid, const char *password) {
  Serial.printf("[RobotNetworkManager] Wi-Fi 연결 시도: %s\n", ssid);

  WiFi.begin(ssid, password);

  // 최대 10초간 연결 대기
  int timeout = 20; // 500ms × 20 = 10초
  while (WiFi.status() != WL_CONNECTED && timeout > 0) {
    delay(500);
    Serial.print(".");
    timeout--;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf(
        "\n[RobotNetworkManager] Wi-Fi 연결 성공! IP: %s, RSSI: %ddBm\n",
        WiFi.localIP().toString().c_str(), WiFi.RSSI());
    return true;
  } else {
    Serial.println("\n[RobotNetworkManager] Wi-Fi 연결 실패");
    return false;
  }
}

// ============================================================
//  서버 TCP 연결
// ============================================================

bool RobotNetworkManager::connectToServer(const char *serverIP,
                                          uint16_t serverPort) {
  _serverIP = serverIP;
  _serverPort = serverPort;

  Serial.printf("[RobotNetworkManager] 서버 TCP 연결 시도: %s:%d\n", serverIP,
                serverPort);

  if (_tcpClient.connect(serverIP, serverPort)) {
    Serial.println("[RobotNetworkManager] 서버 연결 성공");
    return true;
  } else {
    Serial.println("[RobotNetworkManager] 서버 연결 실패");
    return false;
  }
}

// ============================================================
//  서버 연결 유지 (자동 복구)
// ============================================================

static uint8_t robotStateToStatusId(RobotState s) {
  switch (s) {
  case RobotState::FORWARD:
  case RobotState::SOFT_LEFT:
  case RobotState::SOFT_RIGHT:
  case RobotState::HARD_LEFT:
  case RobotState::HARD_RIGHT:
  case RobotState::FINDING_LEFT:
  case RobotState::FINDING_RIGHT:
  case RobotState::FINDING_UTURN:
  case RobotState::PASSING_STRAIGHT:
  case RobotState::BACKWARD:
    return 1;
  case RobotState::OUT_OF_LINE:
    return 4;
  case RobotState::IDLE:
  case RobotState::CROSS_DETECTED:
  case RobotState::ARRIVED:
  default:
    return 2;
  }
}

void RobotNetworkManager::sendSfamTelemetry(int battery) {
  int s1, s2, s3, s4, s5;
  _lineFollower.getSensorValues(s1, s2, s3, s4, s5);
  uint8_t lineMask = (s1 ? 0x10 : 0) | (s2 ? 0x08 : 0) | (s3 ? 0x04 : 0) |
                     (s4 ? 0x02 : 0) | (s5 ? 0x01 : 0);
  int nodeIdx = _lineFollower.getCurrentNodeIndex();
  RobotState state = _lineFollower.getState();
  bool isMoving =
      (state != RobotState::IDLE && state != RobotState::CROSS_DETECTED &&
       state != RobotState::ARRIVED && state != RobotState::OUT_OF_LINE);
  uint8_t currentNodeIdx =
      isMoving ? 0xFF
               : ((nodeIdx >= 0 && nodeIdx < 16) ? (uint8_t)(nodeIdx + 1) : 0);

  int spd = _motorController.getSpeedForward();
  uint8_t pwmVal = (uint8_t)((spd > 0) ? (spd / 17) : 0);
  if (pwmVal > 15)
    pwmVal = 15;
  uint8_t motorPwm = (pwmVal << 4) | pwmVal;

  uint8_t payload[8] = {robotStateToStatusId(state),
                        (uint8_t)(battery & 0xFF),
                        currentNodeIdx,
                        0,
                        0,
                        lineMask,
                        motorPwm,
                        0};
  uint8_t buf[SFAM_PKT_MAX];
  uint8_t len = sfam_build_packet(buf, MSG_AGV_TELEMETRY, ID_AGV_R01, ID_SERVER,
                                  _sfamSeq++, payload, 8);
  _tcpClient.write(buf, len);
}

void RobotNetworkManager::sendSfamHeartbeat() {
  uint8_t buf[SFAM_PKT_MAX];
  uint8_t len = sfam_build_packet(buf, MSG_HEARTBEAT_REQ, ID_AGV_R01, ID_SERVER,
                                  _sfamSeq++, nullptr, 0);
  _tcpClient.write(buf, len);
  Serial.println("[RobotNetworkManager] SFAM HEARTBEAT_REQ 전송");
}

void RobotNetworkManager::sendSfamRfidEvent(const char *uid) {
  if (!_tcpClient.connected() || uid == nullptr)
    return;
  size_t len = strlen(uid);
  if (len > SFAM_MAX_PAYLOAD)
    len = SFAM_MAX_PAYLOAD;
  uint8_t buf[SFAM_PKT_MAX];
  uint8_t pktLen =
      sfam_build_packet(buf, MSG_RFID_EVENT, ID_AGV_R01, ID_SERVER, _sfamSeq++,
                        (const uint8_t *)uid, (uint8_t)len);
  _tcpClient.write(buf, pktLen);
  Serial.printf("[RobotNetworkManager] SFAM RFID_EVENT 전송: %s\n", uid);
}

void RobotNetworkManager::sendSfamTaskAck(uint16_t taskId, uint8_t ackCode) {
  if (!_tcpClient.connected())
    return;
  uint8_t payload[3] = {(uint8_t)(taskId >> 8), (uint8_t)(taskId & 0xFF),
                        ackCode};
  uint8_t buf[SFAM_PKT_MAX];
  uint8_t len = sfam_build_packet(buf, MSG_AGV_TASK_ACK, ID_AGV_R01, ID_SERVER,
                                  _sfamSeq++, payload, 3);
  _tcpClient.write(buf, len);
  Serial.printf("[RobotNetworkManager] SFAM TASK_ACK task=%u ack=%u\n",
                (unsigned)taskId, (unsigned)ackCode);
}

void RobotNetworkManager::sendSfamStatusRpt(uint16_t taskId, uint8_t taskStatus,
                                            uint8_t nodeIdx, uint8_t errorId) {
  if (!_tcpClient.connected())
    return;
  uint8_t payload[5] = {(uint8_t)(taskId >> 8), (uint8_t)(taskId & 0xFF),
                        taskStatus, nodeIdx, errorId};
  uint8_t buf[SFAM_PKT_MAX];
  uint8_t len = sfam_build_packet(buf, MSG_AGV_STATUS_RPT, ID_AGV_R01,
                                  ID_SERVER, _sfamSeq++, payload, 5);
  _tcpClient.write(buf, len);
  Serial.printf(
      "[RobotNetworkManager] SFAM STATUS_RPT task=%u status=%u node=%u\n",
      (unsigned)taskId, (unsigned)taskStatus, (unsigned)nodeIdx);
}

void RobotNetworkManager::processSfamPacket(const uint8_t *pkt,
                                            uint8_t payLen) {
  uint8_t msgType = pkt[1];
  const uint8_t *payload = pkt + 6;

  if (msgType == MSG_AGV_TASK_CMD && payLen >= 10) {
    uint16_t taskId = ((uint16_t)payload[0] << 8) | payload[1];
    uint8_t dstNodeIdx = payload[5];
    int targetIdx =
        (dstNodeIdx >= 1 && dstNodeIdx <= 16) ? (int)(dstNodeIdx - 1) : -1;

    if (_lineFollower.isRunning()) {
      sendSfamTaskAck(taskId, 2);
      return;
    }
    if (targetIdx < 0 || targetIdx >= _pathFinder.getNodeCount()) {
      sendSfamTaskAck(taskId, 1);
      return;
    }
    int startIdx = _lineFollower.getCurrentNodeIndex();
    int startDir = _lineFollower.getCurrentDirection();
    char pathBuf[64];
    int nodeSeq[16];
    int pathLen = _pathFinder.calculatePath(startIdx, targetIdx, startDir,
                                            pathBuf, nodeSeq, 16);
    if (pathLen < 0) {
      sendSfamTaskAck(taskId, 1);
      return;
    }
    int nodeCount = 0;
    for (int i = 0; i < 16 && nodeSeq[i] >= 0; i++)
      nodeCount++;
    _currentTaskId = taskId;
    _lineFollower.setPath(String(pathBuf), nodeSeq, nodeCount);
    _lineFollower.start();
    sendSfamTaskAck(taskId, 0);
    sendSfamStatusRpt(taskId, 1, (uint8_t)(startIdx + 1), 0);
    Serial.printf(
        "[RobotNetworkManager] SFAM TASK_CMD 수락 task=%u dst=%u 경로=%s\n",
        (unsigned)taskId, (unsigned)dstNodeIdx, pathBuf);
  } else if (msgType == MSG_AGV_EMERGENCY && payLen >= 2) {
    uint8_t action = payload[0];
    if (action == 0) {
      _motorController.stop();
      _lineFollower.stop();
      Serial.println("[RobotNetworkManager] SFAM EMERGENCY E-STOP");
    }
  }
}

void RobotNetworkManager::maintainConnection() {
  // Wi-Fi는 연결되어 있는데, 서버 소켓이 끊어진 경우에만 재연결 시도
  if (WiFi.status() != WL_CONNECTED || _tcpClient.connected()) {
    return;
  }
  if (_serverIP == nullptr) {
    return;
  }

  unsigned long now = millis();
  const unsigned long RECONNECT_INTERVAL = 5000; // 5초 간격

  if (now - _lastReconnectAttempt >= RECONNECT_INTERVAL) {
    _lastReconnectAttempt = now;
    Serial.println("[RobotNetworkManager] 서버와 연결이 끊어졌습니다. 재연결을 "
                   "시도합니다...");
    if (_tcpClient.connect(_serverIP, _serverPort)) {
      Serial.println("[RobotNetworkManager] 서버 재연결 성공");
    } else {
      Serial.println("[RobotNetworkManager] 서버 재연결 실패");
    }
  }
}

// ============================================================
//  메인 루프: TCP 수신 데이터 처리
// ============================================================

void RobotNetworkManager::handleIncoming() {
  // 라인트레이싱 업데이트 (매 사이클 실행)
  _lineFollower.update();

  if (_lineFollower.getState() == RobotState::ARRIVED) {
    int nodeIdx = _lineFollower.getCurrentNodeIndex();

    // SFAM 상태 리포트
    if (_currentTaskId != 0) {
      sendSfamStatusRpt(
          _currentTaskId, 2,
          (uint8_t)(nodeIdx >= 0 && nodeIdx < 16 ? nodeIdx + 1 : 0), 0);
      _currentTaskId = 0;
    }

    // ★ 입고 픽업 대기 플래그가 켜져 있으면 A01 도착 후 자동 픽업
    if (_pendingInboundPickup && nodeIdx == 0) { // nodeIdx 0 = A01
      _pendingInboundPickup = false;
      executeInboundPickup();
    }

    // ★ S11 도착 후 자동 하차 (입고 시나리오 연계)
    if (_pendingInboundDrop && nodeIdx == 10) { // nodeIdx 10 = S11
      _pendingInboundDrop = false;
      executeInboundDrop();
    }
  }

  // RFID 태그 읽기 (매 사이클 실행)
  _rfidReader.readTag();
  if (_rfidReader.hasNewTag()) {
    String uid = _rfidReader.getLastTagUID();
    if (uid.length() > 0) {
      sendSfamRfidEvent(uid.c_str());
    }
    _rfidReader.clearNewTagFlag();
  }

  // 서버 연결 유지 (끊어졌으면 재연결 시도)
  maintainConnection();

  // TCP 소켓에 수신 데이터가 있는지 확인
  if (!_tcpClient.connected() || !_tcpClient.available()) {
    return;
  }

  // 바이트 단위 수신: 0xAA면 SFAM, 아니면 JSON(\n까지)
  while (_tcpClient.available()) {
    uint8_t b = _tcpClient.read();

    if (_rxSfamCount == 0 && b == SFAM_SOF) {
      _rxSfamBuf[0] = b;
      _rxSfamCount = 1;
      _rxSfamPayLen = 0;
    } else if (_rxSfamCount > 0) {
      _rxSfamBuf[_rxSfamCount++] = b;
      if (_rxSfamCount == 6) {
        _rxSfamPayLen = _rxSfamBuf[5];
      }
      uint8_t total = 6 + _rxSfamPayLen + 2;
      if (_rxSfamCount >= total) {
        uint16_t calcCrc = sfam_crc16(_rxSfamBuf, 6 + _rxSfamPayLen);
        uint16_t rxCrc = ((uint16_t)_rxSfamBuf[6 + _rxSfamPayLen] << 8) |
                         _rxSfamBuf[6 + _rxSfamPayLen + 1];
        if (calcCrc == rxCrc) {
          processSfamPacket(_rxSfamBuf, _rxSfamPayLen);
        } else {
          Serial.printf(
              "[RobotNetworkManager] SFAM CRC 오류! (수신:%04X 계산:%04X)\n",
              rxCrc, calcCrc);
        }
        _rxSfamCount = 0;
      }
    } else {
      int idx = 0;
      _recvBuffer[idx++] = (char)b;
      while (_tcpClient.available() && idx < (int)sizeof(_recvBuffer) - 1) {
        char c = (char)_tcpClient.read();
        if (c == '\n' || c == '\r')
          break;
        _recvBuffer[idx++] = c;
      }
      _recvBuffer[idx] = '\0';
      if (idx > 0 && _recvBuffer[0] != '\n' && _recvBuffer[0] != '\r') {
        String rawData = String(_recvBuffer);
        Serial.printf("[RobotNetworkManager] 수신: %s\n", rawData.c_str());
        JsonDocument doc;
        if (parseCommand(rawData, doc)) {
          const char *cmd = doc["cmd"];
          if (cmd) {
            if (strcmp(cmd, "MOVE") == 0) {
              handleMove(doc);
            } else if (strcmp(cmd, "GOTO") == 0) {
              handleGoto(doc);
            } else if (strcmp(cmd, "SET_LOC") == 0) {
              handleSetLoc(doc);
            } else if (strcmp(cmd, "TASK") == 0) {
              handleTask(doc);
            } else if (strcmp(cmd, "MANUAL") == 0) {
              handleManual(doc);
            } else {
              Serial.printf("[RobotNetworkManager] 알 수 없는 명령: %s\n", cmd);
              sendResponse("FAIL", "알 수 없는 명령");
            }
          }
        }
      }
    }
  }
}

// ============================================================
//  JSON 파싱
// ============================================================

bool RobotNetworkManager::parseCommand(const String &rawData,
                                       JsonDocument &doc) {
  DeserializationError error = deserializeJson(doc, rawData);

  if (error) {
    Serial.printf("[RobotNetworkManager] JSON 파싱 오류: %s\n", error.c_str());
    return false;
  }

  return true;
}

// ============================================================
//  로봇 상태 TCP 전송
// ============================================================

void RobotNetworkManager::broadcastRobotState(const char *robotId, int posX,
                                              int posY, int battery) {
  /*
   * control-server 연동: SFAM MSG_AGV_TELEMETRY(0x10) 전송
   * 5초마다 MSG_HEARTBEAT_REQ(0x01) 추가 전송
   */
  if (!_tcpClient.connected()) {
    return;
  }

  unsigned long now = millis();
  if (now - _lastHeartbeatMs >= 5000) {
    sendSfamHeartbeat();
    _lastHeartbeatMs = now;
  }
  sendSfamTelemetry(battery);
}

// ============================================================
//  TCP 응답 전송
// ============================================================

void RobotNetworkManager::sendResponse(const char *status, const char *msg) {
  /*
   * 서버에 명령 처리 결과를 TCP로 응답한다.
   *
   * 응답 포맷:
   *   {"status": "SUCCESS", "msg": "도착 완료"}
   */

  JsonDocument doc;
  doc["status"] = status;
  doc["msg"] = msg;

  char jsonBuffer[256];
  serializeJson(doc, jsonBuffer, sizeof(jsonBuffer));

  _tcpClient.println(jsonBuffer);
  Serial.printf("[RobotNetworkManager] 응답 전송: %s\n", jsonBuffer);
}

// ============================================================
//  명령 핸들러 (뼈대 – 팀원이 내부 로직 구현)
// ============================================================

void RobotNetworkManager::handleMove(JsonDocument &doc) {
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
    const char *path = doc["path"];
    unsigned int backMs = doc["crossroad_backward_ms"] | 0;
    Serial.printf("[RobotNetworkManager] 경로 이동 명령 수신 → 경로: %s, "
                  "교차로후진: %ums\n",
                  path, backMs);

    _lineFollower.setCrossroadBackwardMs(backMs);
    _lineFollower.setPath(path);
    _lineFollower.start();

    sendResponse("SUCCESS", "경로 추종 시작");
    return;
  }

  // 노드 기반 이동 (target_node 필드 - control-server task_dispatcher)
  if (doc.containsKey("target_node")) {
    const char *targetNode = doc["target_node"];
    Serial.printf("[RobotNetworkManager] 노드 이동 명령 수신 → 목표: %s\n",
                  targetNode);

    int targetIdx = _pathFinder.nodeNameToIndex(targetNode);
    if (targetIdx < 0 || targetIdx >= _pathFinder.getNodeCount()) {
      sendResponse("FAIL", "잘못된 목표 노드");
      return;
    }
    int startIdx = _lineFollower.getCurrentNodeIndex();
    int startDir = _lineFollower.getCurrentDirection();
    char pathBuf[64];
    int nodeSeq[16];
    int pathLen = _pathFinder.calculatePath(startIdx, targetIdx, startDir,
                                            pathBuf, nodeSeq, 16);
    if (pathLen < 0) {
      sendResponse("FAIL", "경로 탐색 실패");
      return;
    }
    int nodeCount = 0;
    for (int i = 0; i < 16 && nodeSeq[i] >= 0; i++)
      nodeCount++;
    unsigned int backMs = doc["crossroad_backward_ms"] | 0;
    _lineFollower.setCrossroadBackwardMs(backMs);
    _lineFollower.setPath(String(pathBuf), nodeSeq, nodeCount);
    _lineFollower.start();
    Serial.printf("[RobotNetworkManager] MOVE target_node %s → 경로: %s\n",
                  targetNode, pathBuf);
    sendResponse("SUCCESS", "경로 추종 시작");
    return;
  }

  Serial.println(
      "[RobotNetworkManager] MOVE 명령에 path 또는 target_node 필드 없음");
  sendResponse("FAIL", "path 또는 target_node 필드 필요");
}

void RobotNetworkManager::handleGoto(JsonDocument &doc) {
  /*
   * GOTO 명령: PathFinder로 경로 계산 후 LineFollower로 이동.
   * {"cmd": "GOTO", "target": 5} - 노드 인덱스
   * {"cmd": "GOTO", "target_node": "s06"} - 노드 이름
   */
  int targetIdx = -1;
  if (doc.containsKey("target")) {
    targetIdx = doc["target"].as<int>();
  } else if (doc.containsKey("target_node")) {
    const char *nodeName = doc["target_node"];
    targetIdx = _pathFinder.nodeNameToIndex(nodeName);
  }

  if (targetIdx < 0 || targetIdx >= _pathFinder.getNodeCount()) {
    sendResponse("FAIL", "잘못된 목표 노드");
    return;
  }

  int startIdx = _lineFollower.getCurrentNodeIndex();
  int startDir = _lineFollower.getCurrentDirection();

  char pathBuf[64];
  int nodeSeq[16];
  int len = _pathFinder.calculatePath(startIdx, targetIdx, startDir, pathBuf,
                                      nodeSeq, 16);

  if (len < 0) {
    sendResponse("FAIL", "경로 탐색 실패");
    return;
  }

  // 노드 시퀀스 길이 계산 (nodeSeq에서 -1 또는 경로길이+1)
  int nodeCount = 0;
  for (int i = 0; i < 16 && nodeSeq[i] >= 0; i++)
    nodeCount++;

  unsigned int backMs = doc["crossroad_backward_ms"] | 0;
  _lineFollower.setCrossroadBackwardMs(backMs);
  _lineFollower.setPath(String(pathBuf), nodeSeq, nodeCount);
  _lineFollower.start();

  Serial.printf("[RobotNetworkManager] GOTO %d → 경로: %s, 교차로후진: %ums\n",
                targetIdx, pathBuf, backMs);
  sendResponse("SUCCESS", "GOTO 경로 추종 시작");
}

void RobotNetworkManager::handleSetLoc(JsonDocument &doc) {
  /*
   * SET_LOC 명령: 현재 위치 수동 설정 (역추적/초기화용).
   * {"cmd": "SET_LOC", "node": 0, "dir": 1}
   */
  if (!doc.containsKey("node") || !doc.containsKey("dir")) {
    sendResponse("FAIL", "node, dir 필드 필요");
    return;
  }

  int nodeIdx = doc["node"].as<int>();
  int dir = doc["dir"].as<int>();

  if (nodeIdx < 0 || nodeIdx >= _pathFinder.getNodeCount()) {
    sendResponse("FAIL", "잘못된 노드 인덱스");
    return;
  }

  dir = (dir % 4 + 4) % 4;
  _lineFollower.setLocation(nodeIdx, dir, _pathFinder.indexToNodeName(nodeIdx));

  Serial.printf("[RobotNetworkManager] SET_LOC node=%d dir=%d\n", nodeIdx, dir);
  sendResponse("SUCCESS", "위치 설정 완료");
}

bool RobotNetworkManager::setLocationByNodeName(const char *nodeName, int dir) {
  if (nodeName == nullptr) {
    Serial.println(
        "[RobotNetworkManager] setLocationByNodeName: nodeName is null");
    return false;
  }

  int nodeIdx = _pathFinder.nodeNameToIndex(nodeName);
  if (nodeIdx < 0 || nodeIdx >= _pathFinder.getNodeCount()) {
    Serial.printf(
        "[RobotNetworkManager] setLocationByNodeName: 잘못된 노드 이름: %s\n",
        nodeName);
    return false;
  }

  dir = (dir % 4 + 4) % 4;
  _lineFollower.setLocation(nodeIdx, dir, _pathFinder.indexToNodeName(nodeIdx));
  Serial.printf(
      "[RobotNetworkManager] setLocationByNodeName: %s (idx=%d) dir=%d\n",
      nodeName, nodeIdx, dir);
  return true;
}

void RobotNetworkManager::handleTask(JsonDocument &doc) {
  /*
   * 작업 명령 처리 (Pick-and-Place 등).
   * 수신: {"cmd": "TASK", "action": "PICK_READY"}
   *       {"cmd": "TASK", "action": "PICK_EXECUTE"}
   *       {"cmd": "TASK", "action": "DROP"}
   */
  const char *action = doc["action"];
  int count = doc["count"] | 1; // 기본값 1
  Serial.printf("[RobotNetworkManager] 작업 명령 수신 → 동작: %s, 횟수: %d\n",
                action, count);

  if (strcmp(action, "PICK_READY") == 0) {
    _armController.pickReady();
    sendResponse("SUCCESS", "픽업 준비(그리퍼 열기, 팔 내리기) 완료");
  } else if (strcmp(action, "PICK_EXECUTE") == 0) {
    _armController.pickExecute();
    sendResponse("SUCCESS", "픽업 실행(그리퍼 닫기, 팔 올리기) 완료");
  } else if (strcmp(action, "DROP") == 0) {
    _armController.dropPot();
    sendResponse("SUCCESS", "화분 내려놓기 완료");
  } else if (strcmp(action, "ARM_CW_180") == 0) {
    _armController.rotateArm180CW();
    sendResponse("SUCCESS", "암 시계방향 180도 회전 완료");
  } else if (strcmp(action, "ARM_CCW_180") == 0) {
    _armController.rotateArm180CCW();
    sendResponse("SUCCESS", "암 반시계방향 180도 회전 완료");
  } else if (strcmp(action, "GRIPPER_GRAB") == 0) {
    _armController.grabGripper();
    sendResponse("SUCCESS", "그리퍼 잡기 완료");
  } else if (strcmp(action, "GRIPPER_RELEASE") == 0) {
    _armController.releaseGripper();
    sendResponse("SUCCESS", "그리퍼 놓기 완료");
  } else if (strcmp(action, "INBOUND_PICKUP") == 0) {
    // ★ 입고 명령: A01로 이동 후 자동 픽업 시퀀스
    Serial.println("[RobotNetworkManager] ★ 입고 명령 수신! A01로 이동 시작");

    int targetIdx = _pathFinder.nodeNameToIndex("a01");
    if (targetIdx < 0) {
      sendResponse("FAIL", "A01 노드를 찾을 수 없음");
      return;
    }
    int startIdx = _lineFollower.getCurrentNodeIndex();
    int startDir = _lineFollower.getCurrentDirection();
    char pathBuf[64];
    int nodeSeq[16];
    int pathLen = _pathFinder.calculatePath(startIdx, targetIdx, startDir,
                                            pathBuf, nodeSeq, 16);
    if (pathLen < 0) {
      sendResponse("FAIL", "A01까지 경로 탐색 실패");
      return;
    }
    int nodeCount = 0;
    for (int i = 0; i < 16 && nodeSeq[i] >= 0; i++)
      nodeCount++;

    _pendingInboundPickup = true; // 도착 후 자동 픽업 플래그 ON
    _lineFollower.setPath(String(pathBuf), nodeSeq, nodeCount);
    _lineFollower.start();
    Serial.printf(
        "[RobotNetworkManager] 입고 경로: %s (도착 후 자동 픽업 예정)\n",
        pathBuf);
    sendResponse("SUCCESS", "입고 명령 수락 - A01로 이동 중");
  } else if (strcmp(action, "U_TURN_TEST") == 0) {
    // 단독 U턴 테스트 (첫 가로선에서 바로 U턴)
    Serial.println("[RobotNetworkManager] 🔄 첫 가로선 U턴 테스트 명령 수신");

    // 경로 명령 'U': 첫 번째 교차로에서 즉시 U턴
    int nodeSeq[1] = {_lineFollower.getCurrentNodeIndex()};
    _lineFollower.setPath("U", nodeSeq, 1);
    _lineFollower.start();

    sendResponse("SUCCESS", "첫 가로선 U턴 테스트 시작");
  } else {
    sendResponse("FAIL", "알 수 없는 작업 명령");
  }
}

void RobotNetworkManager::executeInboundPickup() {
  /*
   * ★ A01 도착 후 입고 픽업 시퀀스
   *
   * 초기 상태: 그리퍼 열림, 암 안쪽(수축)
   *
   * 1. U턴 (180도 회전) - 트레이 쪽을 향하도록
   * 2. 암 내리기 (CW 180도) - 팔을 트레이 쪽으로 뻗기
   * 3. 후진 (INBOUND_BACKWARD_MS) - 트레이에 밀착
   * 4. 그리퍼 닫기 - 화분 잡기
   * 5. 암 올리기 (CCW 180도) - 화분 들어올리기
   * 6. S11로 이동
   */
  Serial.println("\n======================================");
  Serial.println("  ★ 입고 픽업 시퀀스 시작");
  Serial.println("======================================");

  // 1. U턴 (180도 회전) - U턴 테스트 버튼과 100% 동일한 코드 경로 사용
  //    LineFollower에 경로 "U"를 넣고 실행 → executeCrossroadCommand의 UTURN 케이스 사용
  Serial.println("[입고 1/6] U턴 실행 (U턴 테스트와 동일 경로)...");
  {
    int nodeSeq[1] = {_lineFollower.getCurrentNodeIndex()};
    _lineFollower.setPath("U", nodeSeq, 1);
    _lineFollower.start();
    // U턴이 완료될 때까지 대기 (update 루프)
    while (_lineFollower.isRunning()) {
      _lineFollower.update();
      delay(5);
    }
    _motorController.stop();
    delay(500);
  }
  Serial.println("[입고 1/6] U턴 완료!");

  // 2. 암 내리기 (CW 180도 - 팔 뻗기)
  Serial.println("[입고 2/6] 암 내리기 (CW 180도)...");
  _armController.rotateArmCW();
  Serial.println("[입고 2/6] 암 내리기 완료!");

  // 3. 후진 (트레이에 밀착)
  Serial.printf("[입고 3/6] 후진 %dms...\n", INBOUND_BACKWARD_MS);
  _motorController.goBackward();
  delay(INBOUND_BACKWARD_MS);
  _motorController.stop();
  delay(500);
  Serial.println("[입고 3/6] 후진 완료!");

  // 4. 그리퍼 닫기 (화분 잡기)
  Serial.println("[입고 4/6] 그리퍼 닫기...");
  _armController.grabGripper();
  Serial.println("[입고 4/6] 그리퍼 닫기 완료!");

  // 5. 암 올리기 (CCW 180도 - 팔 수축)
  Serial.println("[입고 5/6] 암 올리기 (CCW 180도)...");
  _armController.rotateArmCCW();
  Serial.println("[입고 5/6] 암 올리기 완료!");

  Serial.println("\n======================================");
  Serial.println("  ★ 픽업 완료! S11로 이동 시작");
  Serial.println("======================================\n");

  // 6. S11로 이동
  // 현재 방향은 U턴 후이므로 E방향 (A01에서 A02를 바라봄)
  _lineFollower.setLocation(0, 1, "a01"); // A01, E방향
  int targetIdx = _pathFinder.nodeNameToIndex("s11");
  if (targetIdx >= 0) {
    int startIdx = 0; // A01
    int startDir = 1; // E
    char pathBuf[64];
    int nodeSeq[16];
    int pathLen = _pathFinder.calculatePath(startIdx, targetIdx, startDir,
                                            pathBuf, nodeSeq, 16);
    if (pathLen >= 0) {
      int nodeCount = 0;
      for (int i = 0; i < 16 && nodeSeq[i] >= 0; i++)
        nodeCount++;

      _pendingInboundDrop = true; // S11 도착 후 하차 시퀀스 플래그 ON

      _lineFollower.setPath(String(pathBuf), nodeSeq, nodeCount);
      _lineFollower.start();
      Serial.printf("[입고 6/6] S11 이동 경로: %s\n", pathBuf);
    } else {
      Serial.println("[입고 6/6] S11 경로 탐색 실패!");
    }
  } else {
    Serial.println("[입고 6/6] S11 노드를 찾을 수 없음!");
  }
}

void RobotNetworkManager::executeInboundDrop() {
  /*
   * ★ S11 도착 후 입고 하차 시퀀스
   * 1. 후진 (0.5s) - 슬롯 체결/안정용
   * 2. 화분 내려놓기
   */
  Serial.println("\n======================================");
  Serial.println("  ★ 입고 하차 시퀀스 시작 (S11)");
  Serial.println("======================================");

  // 1. 후진 (0.5초)
  Serial.printf("[하차 1/2] 후진 %dms...\n", INBOUND_DROP_BACKWARD_MS);
  _motorController.goBackward();
  delay(INBOUND_DROP_BACKWARD_MS);
  _motorController.stop();
  delay(500);
  Serial.println("[하차 1/2] 후진 완료!");

  // 2. 화분 내려놓기
  Serial.println("[하차 2/2] 암 내리고 그리퍼 열기...");
  _armController.dropPot();
  Serial.println("[하차 2/2] 하차 완료!");

  Serial.println("\n======================================");
  Serial.println("  ★ 픽업 및 하차 전체 시퀀스 종료!");
  Serial.println("======================================\n");
}

void RobotNetworkManager::handleManual(JsonDocument &doc) {
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
  const char *device = doc["device"];
  const char *state = doc["state"];
  Serial.printf("[RobotNetworkManager] 수동 제어 수신 → 장치: %s, 상태: %s\n",
                device, state);

  // TODO: GPIO 핀 제어 로직 구현
  // int pin = getPinForDevice(device);
  // digitalWrite(pin, strcmp(state, "ON") == 0 ? HIGH : LOW);

  sendResponse("SUCCESS", "수동 제어 수신 확인");
}
