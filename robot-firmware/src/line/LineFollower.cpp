/**
 * LineFollower.cpp
 * ================
 * ESP32 로봇 라인트레이싱 및 경로 추종 구현 파일.
 */

#include "LineFollower.h"

// ============================================================
//  생성자
// ============================================================

LineFollower::LineFollower(MotorController& motor)
    : _motor(motor)
    , _pathString("")
    , _currentStep(0)
    , _isRunning(false)
    , _state(RobotState::IDLE)
    , _nodeName("-")
    , _s1(0), _s2(0), _s3(0), _s4(0), _s5(0)
{
}

// ============================================================
//  경로 설정 및 제어
// ============================================================

void LineFollower::setPath(const String& path) {
    _pathString = path;
    _currentStep = 0;
    Serial.printf("[LineFollower] 경로 설정: %s\n", path.c_str());
}

void LineFollower::start() {
    if (_pathString.length() == 0) {
        Serial.println("[LineFollower] ⚠️ 경로가 설정되지 않음");
        return;
    }
    _isRunning = true;
    _currentStep = 0;
    _state = RobotState::FORWARD;
    _nodeName = "출발";
    Serial.println("[LineFollower] 🚀 주행 시작");
}

void LineFollower::stop() {
    _isRunning = false;
    _state = RobotState::IDLE;
    _motor.stop();
    Serial.println("[LineFollower] 🛑 주행 정지");
}

// ============================================================
//  메인 업데이트 루프
// ============================================================

void LineFollower::update() {
    // 센서 읽기
    _motor.readSensors(_s1, _s2, _s3, _s4, _s5);

    // 주행 중이 아니면 대기
    if (!_isRunning) {
        _state = RobotState::IDLE;
        _motor.stop();
        return;
    }

    // 교차로 감지 확인
    if (detectCrossroad(_s1, _s2, _s3, _s4, _s5)) {
        _state = RobotState::CROSS_DETECTED;
        _motor.stop();
        delay(500);

        // 노드 이름 갱신 (A1, A2, A3, ...)
        _nodeName = "A" + String(_currentStep + 1);

        // 경로 명령 실행
        executeCrossroadCommand();
        return;
    }

    // 일반 라인트레이싱
    followLine(_s1, _s2, _s3, _s4, _s5);

    delay(10);
}

// ============================================================
//  교차로 감지
// ============================================================

bool LineFollower::detectCrossroad(int s1, int s2, int s3, int s4, int s5) {
    // 양쪽 끝 센서가 동시에 감지되거나
    // 양쪽 센서가 감지되고 중앙이 비어있는 경우
    return (s1 == 1 && s5 == 1) || (s2 == 1 && s4 == 1 && s3 == 0);
}

// ============================================================
//  교차로 명령 실행
// ============================================================

void LineFollower::executeCrossroadCommand() {
    // 경로 끝 확인
    if (_currentStep >= (int)_pathString.length()) {
        _state = RobotState::ARRIVED;
        _nodeName = "도착";
        _isRunning = false;
        Serial.println("[LineFollower] ✅ 목적지 도착");
        return;
    }

    // 다음 명령 가져오기
    int cmdValue = _pathString.charAt(_currentStep) - '0';
    PathCommand cmd = static_cast<PathCommand>(cmdValue);

    switch (cmd) {
        case PathCommand::END:
            _state = RobotState::ARRIVED;
            _nodeName = "도착";
            _isRunning = false;
            Serial.println("[LineFollower] ✅ 목적지 도착 (E 명령)");
            break;

        case PathCommand::LEFT:
            Serial.println("[LineFollower] ⬅️ 좌회전 실행");
            _state = RobotState::FINDING_LEFT;
            _motor.goForward();
            delay(150);
            _motor.turnLeftHard();
            delay(250);
            waitForLineAfterLeft();
            break;

        case PathCommand::RIGHT:
            Serial.println("[LineFollower] ➡️ 우회전 실행");
            _state = RobotState::FINDING_RIGHT;
            _motor.goForward();
            delay(150);
            _motor.turnRightHard();
            delay(250);
            waitForLineAfterRight();
            break;

        case PathCommand::UTURN:
            Serial.println("[LineFollower] ↩️ U턴 실행");
            _state = RobotState::FINDING_UTURN;
            _motor.goForward();
            delay(150);
            _motor.uTurnRight();
            delay(250);
            waitForLineAfterUturn();
            break;

        case PathCommand::STRAIGHT:
            Serial.println("[LineFollower] ⬆️ 직진 통과");
            _state = RobotState::PASSING_STRAIGHT;
            _motor.goForward();
            delay(300);
            break;

        default:
            Serial.printf("[LineFollower] ⚠️ 알 수 없는 명령: %d\n", cmdValue);
            break;
    }

    _currentStep++;
}

// ============================================================
//  라인트레이싱
// ============================================================

void LineFollower::followLine(int s1, int s2, int s3, int s4, int s5) {
    // 중앙 센서만 감지: 직진
    if (s3 == 1 && s1 == 0 && s5 == 0) {
        _state = RobotState::FORWARD;
        _motor.goForward();
    }
    // 좌측 센서 감지 (끝 제외): 부드러운 좌회전
    else if (s2 == 1 && s1 == 0) {
        _state = RobotState::SOFT_LEFT;
        _motor.turnLeftSoft();
    }
    // 우측 센서 감지 (끝 제외): 부드러운 우회전
    else if (s4 == 1 && s5 == 0) {
        _state = RobotState::SOFT_RIGHT;
        _motor.turnRightSoft();
    }
    // 좌측 끝 센서 감지: 급격한 좌회전
    else if (s1 == 1) {
        _state = RobotState::HARD_LEFT;
        _motor.turnLeftHard();
    }
    // 우측 끝 센서 감지: 급격한 우회전
    else if (s5 == 1) {
        _state = RobotState::HARD_RIGHT;
        _motor.turnRightHard();
    }
    // 라인 이탈
    else {
        _state = RobotState::OUT_OF_LINE;
        _motor.stop();
    }
}

// ============================================================
//  회전 후 라인 안착 대기
// ============================================================

void LineFollower::waitForLineAfterLeft() {
    int s2, s3, s4;
    int dummy1, dummy5;
    while (true) {
        _motor.readSensors(dummy1, s2, s3, s4, dummy5);
        // 중앙 센서와 양쪽 중 하나가 감지되면 안착 완료
        if (s3 == 1 && (s2 == 1 || s4 == 1)) {
            break;
        }
    }
}

void LineFollower::waitForLineAfterRight() {
    int s2, s3, s4;
    int dummy1, dummy5;
    while (true) {
        _motor.readSensors(dummy1, s2, s3, s4, dummy5);
        if (s3 == 1 && (s2 == 1 || s4 == 1)) {
            break;
        }
    }
}

void LineFollower::waitForLineAfterUturn() {
    int s1, s2, s3, s4, s5;

    // 1. 출발선 지나가기 (눈 감기)
    // 이미 delay(250)로 처리됨

    // 2. 가짜 라인 통과 (첫 번째 라인 감지 후 통과)
    while (true) {
        _motor.readSensors(s1, s2, s3, s4, s5);
        if (s3 == 1 || s4 == 1) break;
    }
    while (true) {
        _motor.readSensors(s1, s2, s3, s4, s5);
        if (s1 == 0 && s2 == 0 && s3 == 0 && s4 == 0 && s5 == 0) break;
    }

    // 3. 진짜 라인 (180도 후) 안착
    while (true) {
        _motor.readSensors(s1, s2, s3, s4, s5);
        if (s3 == 1 && (s2 == 1 || s4 == 1)) {
            break;
        }
    }
}

// ============================================================
//  센서 값 조회
// ============================================================

void LineFollower::getSensorValues(int& s1, int& s2, int& s3, int& s4, int& s5) const {
    s1 = _s1;
    s2 = _s2;
    s3 = _s3;
    s4 = _s4;
    s5 = _s5;
}
