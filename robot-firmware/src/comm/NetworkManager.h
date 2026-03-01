/**
 * NetworkManager.h
 * ================
 * ESP32 로봇 펌웨어용 네트워크 통신 매니저 헤더 파일.
 *
 * 역할:
 *   - Wi-Fi 연결 관리
 *   - 중앙 서버와 TCP 통신 (제어 명령 수신 / 응답 전송)
 *   - 서버로 UDP 상태 브로드캐스트 (위치, 배터리 등)
 *   - ArduinoJson 라이브러리를 이용한 JSON 파싱/생성
 *   - 라인트레이싱 경로 추종 제어
 *
 * [수신 명령 포맷 – TCP]
 *   이동(경로): {"cmd": "MOVE", "path": "12345"}  (1=L, 2=R, 3=U, 4=S, 5=E)
 *   이동(노드): {"cmd": "MOVE", "target_node": "NODE-A1-001"}
 *   작업:  {"cmd": "TASK", "action": "PICK_AND_PLACE", "count": 5}
 *   수동:  {"cmd": "MANUAL", "device": "FAN", "state": "ON"}
 *
 * [송신 응답 포맷 – TCP]
 *   {"status": "SUCCESS", "msg": "도착 완료"}
 *
 * [송신 상태 포맷 – UDP]
 *   {"type": "ROBOT_STATE", "robot_id": "R01", "pos_x": 120, "pos_y": 350, "battery": 80,
 *    "state": 1, "node": "A1", "sensors": [0,1,1,1,0]}
 */

#ifndef NETWORK_MANAGER_H
#define NETWORK_MANAGER_H

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClient.h>
#include <WiFiUdp.h>
#include <ArduinoJson.h>

#include "../motor/MotorController.h"
#include "../line/LineFollower.h"

/**
 * @brief ESP32 로봇의 네트워크 통신을 총괄하는 매니저 클래스.
 *
 * 팀원 가이드:
 *   - 명령 수신 콜백을 등록하면, TCP 명령이 들어올 때 자동으로 호출됩니다.
 *   - UDP 상태 전송은 주기적으로 broadcastRobotState()를 호출하세요.
 */
class NetworkManager {
public:
    // ─────────── 생성자 / 소멸자 ───────────
    NetworkManager();
    ~NetworkManager();

    // ─────────── 초기화 ───────────
    /**
     * @brief 모터 컨트롤러 및 라인트레이서 초기화.
     *        setup()에서 Wi-Fi 연결 전에 호출해야 함.
     */
    void initHardware();

    // ─────────── Wi-Fi 연결 ───────────
    /**
     * @brief Wi-Fi에 연결한다.
     * @param ssid     Wi-Fi SSID
     * @param password Wi-Fi 비밀번호
     * @return 연결 성공 여부
     */
    bool connectWiFi(const char* ssid, const char* password);

    // ─────────── 서버 연결 (TCP) ───────────
    /**
     * @brief 중앙 서버에 TCP 연결한다.
     * @param serverIP   서버 IP 주소
     * @param serverPort 서버 TCP 포트 번호
     * @return 연결 성공 여부
     */
    bool connectToServer(const char* serverIP, uint16_t serverPort);

    // ─────────── 메인 루프 처리 ───────────
    /**
     * @brief loop()에서 매 사이클 호출.
     *        TCP 소켓에서 데이터를 수신하고, 명령이 있으면 파싱하여 처리한다.
     *        또한 라인트레이싱 로직을 업데이트한다.
     */
    void handleIncoming();

    // ─────────── 라인트레이서 접근 ───────────
    /**
     * @brief LineFollower 객체 참조 반환 (외부에서 상태 조회용).
     */
    LineFollower& getLineFollower() { return _lineFollower; }
    const LineFollower& getLineFollower() const { return _lineFollower; }

    // ─────────── 로봇 상태 UDP 브로드캐스트 ───────────
    /**
     * @brief 로봇의 현재 상태를 UDP로 서버에 전송한다.
     * @param robotId  로봇 식별 ID (예: "R01")
     * @param posX     현재 X 좌표
     * @param posY     현재 Y 좌표
     * @param battery  배터리 잔량 (%)
     *
     * 송신 포맷:
     *   {"type": "ROBOT_STATE", "robot_id": "R01", "pos_x": 120, "pos_y": 350, "battery": 80}
     */
    void broadcastRobotState(const char* robotId, int posX, int posY, int battery);

    // ─────────── TCP 응답 전송 ───────────
    /**
     * @brief 서버에 명령 처리 결과를 TCP로 응답한다.
     * @param status 처리 결과 ("SUCCESS" 또는 "FAIL")
     * @param msg    결과 메시지
     *
     * 응답 포맷:
     *   {"status": "SUCCESS", "msg": "도착 완료"}
     */
    void sendResponse(const char* status, const char* msg);

private:
    // ─────────── TCP 명령 파싱 ───────────
    /**
     * @brief 수신된 JSON 문자열을 파싱하여 ArduinoJson Document로 변환한다.
     * @param rawData  수신된 원시 문자열
     * @param doc      파싱 결과를 저장할 JsonDocument 참조
     * @return 파싱 성공 여부
     */
    bool parseCommand(const String& rawData, JsonDocument& doc);

    // ─────────── 명령별 핸들러 (팀원이 내부 로직 구현) ───────────

    /**
     * @brief 이동 명령 처리.
     *        수신 포맷 1 (경로): {"cmd": "MOVE", "path": "12345"}
     *        수신 포맷 2 (노드): {"cmd": "MOVE", "target_node": "NODE-A1-001"}
     *
     *   path 필드가 있으면 라인트레이싱 경로 추종 시작.
     *   target_node 필드만 있으면 기존 방식으로 처리.
     */
    void handleMove(JsonDocument& doc);

    /**
     * @brief 작업 명령 처리 (Pick-and-Place 등).
     *        수신: {"cmd": "TASK", "action": "PICK_AND_PLACE", "count": 5}
     *
     * TODO (팀원 구현):
     *   1) action, count 값 추출
     *   2) so-arm(STS3215 서보) 제어 함수 호출
     *   3) 작업 완료 후 sendResponse() 호출
     */
    void handleTask(JsonDocument& doc);

    /**
     * @brief 수동 제어 명령 처리.
     *        수신: {"cmd": "MANUAL", "device": "FAN", "state": "ON"}
     *
     * TODO (팀원 구현):
     *   1) device, state 값 추출
     *   2) 해당 GPIO 핀 제어
     *   3) 제어 완료 후 sendResponse() 호출
     */
    void handleManual(JsonDocument& doc);

    // ─────────── 멤버 변수 ───────────
    WiFiClient  _tcpClient;     // TCP 클라이언트 소켓
    WiFiUDP     _udpClient;     // UDP 소켓

    const char* _serverIP;      // 서버 IP 주소
    uint16_t    _serverPort;    // 서버 TCP 포트
    uint16_t    _udpPort;       // UDP 브로드캐스트 포트

    char _recvBuffer[1024];     // TCP 수신 버퍼

    // ─────────── 모터 및 라인트레이싱 ───────────
    MotorController _motorController;   // 모터 컨트롤러
    LineFollower    _lineFollower;      // 라인트레이서
};

#endif // NETWORK_MANAGER_H
