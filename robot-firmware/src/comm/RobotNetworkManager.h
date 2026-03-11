/**
 * RobotNetworkManager.h
 * =====================
 * ESP32 로봇 펌웨어용 네트워크 통신 매니저 헤더 파일.
 */

#ifndef ROBOT_NETWORK_MANAGER_H
#define ROBOT_NETWORK_MANAGER_H

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClient.h>
#include <WiFiUdp.h>
#include <ArduinoJson.h>

#include "SFAM_Protocol.h"
#include "../motor/MotorController.h"
#include "../line/LineFollower.h"
#include "../path/PathFinder.h"
#include "../rfid/RFIDReader.h"

enum class RobotState; // 전방 선언이 필요할 수 있음

class RobotNetworkManager {
public:
    RobotNetworkManager();
    ~RobotNetworkManager();

    void initHardware();
    bool connectWiFi(const char* ssid, const char* password);
    bool connectToServer(const char* serverIP, uint16_t serverPort);
    void maintainConnection();
    void handleIncoming();

    LineFollower& getLineFollower() { return _lineFollower; }
    const LineFollower& getLineFollower() const { return _lineFollower; }

    RFIDReader& getRFIDReader() { return _rfidReader; }
    const RFIDReader& getRFIDReader() const { return _rfidReader; }

    bool setLocationByNodeName(const char* nodeName, int dir);
    void setRobotId(uint8_t id) { _robotId = id; }
    
    // 상태 및 응답
    void broadcastRobotState();
    void broadcastRobotState(const char* robotId, int posX, int posY, int battery);
    void sendResponse(const char* status, const char* msg);

private:
    bool parseCommand(const String& rawData, JsonDocument& doc);
    
    void handleMove(JsonDocument& doc);
    void handleGoto(JsonDocument& doc);
    void handleSetLoc(JsonDocument& doc);
    void handleTask(JsonDocument& doc);
    void handleManual(JsonDocument& doc);
    
    void sendSfamTelemetry(int battery);
    void sendSfamHeartbeat();
    void sendSfamRfidEvent(const char* uid);
    void sendSfamTaskAck(uint16_t taskId, uint8_t ackCode);
    void sendSfamStatusRpt(uint16_t taskId, uint8_t taskStatus, uint8_t nodeIdx, uint8_t errorId);

    void processSfamPacket(const uint8_t* pkt, uint8_t payLen);

    WiFiClient  _tcpClient;
    WiFiUDP     _udpClient;

    const char* _serverIP;
    uint16_t    _serverPort;
    uint16_t    _udpPort;

    char _recvBuffer[1024];
    uint8_t _rxSfamBuf[SFAM_PKT_MAX];
    uint8_t _rxSfamCount;
    uint8_t _rxSfamPayLen;

    uint8_t  _robotId;
    uint8_t  _tcpSeq;
    unsigned long _msgCount;
    unsigned long _lastReconnectAttempt;
    unsigned long _lastHeartbeatMs;
    uint8_t _sfamSeq;
    uint16_t _currentTaskId;

    MotorController _motorController;
    LineFollower    _lineFollower;
    PathFinder      _pathFinder;
    RFIDReader      _rfidReader;
};

#endif // ROBOT_NETWORK_MANAGER_H
