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
    , _currentIdx(0)
    , _currentDir(0)
    , _pathNodeCount(0)
    , _s1(0), _s2(0), _s3(0), _s4(0), _s5(0)
    , _crossroadBackwardMs(0)
    , _isBackwardUntilCrossroad(false)
    , _backwardStartedOnCross(false)
    , _backwardPhase(0)
    , _backwardStartTime(0)
    , _backwardStepDelta(0)
{
    for (int i = 0; i < 16; i++) _pathNodeSeq[i] = -1;
}

// ============================================================
//  경로 설정 및 제어
// ============================================================

void LineFollower::setPath(const String& path) {
    _pathString = path;
    _currentStep = 0;
    _pathNodeCount = 0;
    Serial.printf("[LineFollower] 경로 설정: %s\n", path.c_str());
}

void LineFollower::setPath(const String& path, const int* nodeSeq, int nodeCount) {
    _pathString = path;
    _currentStep = 0;
    _pathNodeCount = 0;
    if (nodeSeq != nullptr && nodeCount > 0) {
        for (int i = 0; i < nodeCount && i < 16; i++) {
            _pathNodeSeq[i] = nodeSeq[i];
            _pathNodeCount++;
        }
    }
    Serial.printf("[LineFollower] 경로 설정(노드추적): %s\n", path.c_str());
}

void LineFollower::setLocation(int nodeIdx, int dir, const char* nodeName) {
    _currentIdx = nodeIdx;
    _currentDir = (dir + 4) % 4;
    _nodeName = (nodeName != nullptr && nodeName[0] != '\0')
        ? String(nodeName) : getRealNodeName(nodeIdx);
}

String LineFollower::getRealNodeName(int nodeIdx) const {
    static const char* NODE_NAMES[16] = {
        "a01", "a02", "a03", "a04",
        "s05", "s06", "s07",
        "r08", "r09", "r10",
        "s11", "s12", "s13",
        "r14", "r15", "r16"
    };
    if (nodeIdx >= 0 && nodeIdx < 16) {
        return String(NODE_NAMES[nodeIdx]);
    }
    return "UNKNOWN";
}

PathCommand LineFollower::charToPathCommand(char c) const {
    switch (c) {
        case 'L': return PathCommand::LEFT;
        case 'R': return PathCommand::RIGHT;
        case 'U': return PathCommand::UTURN;
        case 'S': return PathCommand::STRAIGHT;
        case 'E': return PathCommand::END;
        case 'B': return PathCommand::BACKWARD;
        default:  return PathCommand::NONE;
    }
}

void LineFollower::start() {
    if (_pathString.length() == 0) {
        Serial.println("[LineFollower] ⚠️ 경로가 설정되지 않음");
        return;
    }
    _isRunning = true;
    _currentStep = 0;
    _state = RobotState::FORWARD;
    if (_pathNodeCount > 0) {
        _currentIdx = _pathNodeSeq[0];
        _nodeName = getRealNodeName(_currentIdx);
    } else {
        _nodeName = "출발";
    }
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
    // 센서 읽기 (전진/후진 공통 - 매 사이클마다)
    _motor.readSensors(_s1, _s2, _s3, _s4, _s5);

    // 주행 중이 아니면 대기
    if (!_isRunning) {
        _state = RobotState::IDLE;
        _motor.stop();
        _isBackwardUntilCrossroad = false;
        return;
    }

    // 후진 모드: 전진과 동일하게 매 사이클마다 followLineBackward 보정
    if (_isBackwardUntilCrossroad) {
        _state = RobotState::BACKWARD;
        const unsigned long SAFETY_MS = 15000;

        if (_backwardPhase == 0) {
            // B 전용: 최소 후진 시간
            unsigned int exitMs = _crossroadBackwardMs > 0 ? _crossroadBackwardMs : 400;
            if (millis() - _backwardStartTime < exitMs) {
                followLineBackward(_s1, _s2, _s3, _s4, _s5);
                return;
            }
            _backwardPhase = 1;
        }
        if (_backwardPhase == 1) {
            // 교차로 탈출 (LB/RB/UB/SB: 교차로 위에 남아 있을 수 있음)
            if (detectCrossroad(_s1, _s2, _s3, _s4, _s5)) {
                followLineBackward(_s1, _s2, _s3, _s4, _s5);
                return;
            }
            Serial.println("[LineFollower] 후진 (다음 교차로까지)");
            _backwardPhase = 2;
        }
        if (_backwardPhase == 2) {
            if (detectCrossroad(_s1, _s2, _s3, _s4, _s5) || (millis() - _backwardStartTime >= SAFETY_MS)) {
                _motor.stop();
                delay(200);
                _isBackwardUntilCrossroad = false;
                _currentStep += _backwardStepDelta;
                return;
            }
            followLineBackward(_s1, _s2, _s3, _s4, _s5);
        }
        return;
    }

    // 교차로 감지 확인
    if (detectCrossroad(_s1, _s2, _s3, _s4, _s5)) {
        _state = RobotState::CROSS_DETECTED;
        _motor.stop();
        delay(500);

        // 노드 이름 갱신 (노드 시퀀스 있으면 해당 인덱스, 없으면 A1, A2...)
        if (_pathNodeCount > 0 && _currentStep < _pathNodeCount) {
            _nodeName = getRealNodeName(_pathNodeSeq[_currentStep]);
        } else {
            _nodeName = "Node_" + String(_currentStep + 1);
        }
        Serial.printf("[LineFollower] 교차로 도착: %s\n", _nodeName.c_str());

        // 경로 명령 실행
        executeCrossroadCommand();
        return;
    }

    // 일반 라인트레이싱
    followLine(_s1, _s2, _s3, _s4, _s5);

    delay(5);
}

// ============================================================
//  후진 - 다음 교차로까지
// ============================================================

void LineFollower::runBackwardUntilCrossroad(bool startedOnCross) {
    _isBackwardUntilCrossroad = true;
    _backwardStartedOnCross = startedOnCross;
    _backwardStartTime = millis();
    _backwardPhase = startedOnCross ? 0 : 1;  // B: 0부터, LB/RB/UB/SB: 1(교차로 탈출)부터
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

    // 다음 명령 가져오기 (숫자 1-6 또는 문자 LRUSEB)
    char pathChar = _pathString.charAt(_currentStep);
    PathCommand cmd;
    if (pathChar >= '1' && pathChar <= '6') {
        cmd = static_cast<PathCommand>(pathChar - '0');
    } else {
        cmd = charToPathCommand(pathChar);
    }

    int stepDelta = 1;  // LB/RB/UB/SB 시 2로 변경

    switch (cmd) {
        case PathCommand::END:
            _state = RobotState::ARRIVED;
            if (_pathNodeCount > 0 && _currentStep < _pathNodeCount) {
                _currentIdx = _pathNodeSeq[_currentStep];
                _nodeName = getRealNodeName(_currentIdx);
            } else {
                _nodeName = "도착";
            }
            _isRunning = false;
            Serial.println("[LineFollower] ✅ 목적지 도착 (E 명령)");
            break;

        case PathCommand::LEFT: {
            Serial.printf("[LineFollower] ⬅️ 좌회전 실행\n");
            _state = RobotState::FINDING_LEFT;
            _currentDir = (_currentDir + 3) % 4;
            if (_pathNodeCount > 0 && _currentStep + 1 < _pathNodeCount) {
                _currentIdx = _pathNodeSeq[_currentStep + 1];
                _nodeName = getRealNodeName(_currentIdx);
            }
            _motor.goForward();
            delay(200);
            _motor.turnLeftHard();
            delay(500);
            waitForLineAfterLeft();
            break;
        }

        case PathCommand::RIGHT: {
            Serial.printf("[LineFollower] ➡️ 우회전 실행\n");
            _state = RobotState::FINDING_RIGHT;
            _currentDir = (_currentDir + 1) % 4;
            if (_pathNodeCount > 0 && _currentStep + 1 < _pathNodeCount) {
                _currentIdx = _pathNodeSeq[_currentStep + 1];
                _nodeName = getRealNodeName(_currentIdx);
            }
            _motor.goForward();
            delay(200);
            _motor.turnRightHard();
            delay(500);
            waitForLineAfterRight();
            break;
        }

        case PathCommand::UTURN: {
            Serial.printf("[LineFollower] ↩️ U턴 실행\n");
            _state = RobotState::FINDING_UTURN;
            _currentDir = (_currentDir + 2) % 4;
            if (_pathNodeCount > 0 && _currentStep + 1 < _pathNodeCount) {
                _currentIdx = _pathNodeSeq[_currentStep + 1];
                _nodeName = getRealNodeName(_currentIdx);
            }
            _motor.goForward();
            delay(150);
            _motor.uTurnRight();
            delay(350);
            waitForLineAfterUturn();
            break;
        }

        case PathCommand::STRAIGHT: {
            Serial.printf("[LineFollower] ⬆️ 직진 통과\n");
            _state = RobotState::PASSING_STRAIGHT;
            if (_pathNodeCount > 0 && _currentStep + 1 < _pathNodeCount) {
                _currentIdx = _pathNodeSeq[_currentStep + 1];
                _nodeName = getRealNodeName(_currentIdx);
            }
            _motor.goForward();
            delay(300);
            break;
        }

        case PathCommand::BACKWARD: {
            runBackwardUntilCrossroad(true);
            _backwardStepDelta = 1;
            stepDelta = 0;
            break;
        }

        default:
            Serial.printf("[LineFollower] ⚠️ 알 수 없는 명령: %c\n", pathChar);
            break;
    }

    _currentStep += stepDelta;
}

// ============================================================
//  라인트레이싱
// ============================================================

void LineFollower::followLine(int s1, int s2, int s3, int s4, int s5) {
    // 중앙 센서만 감지 (s2, s4 없음): 직진
    if (s3 == 1 && s1 == 0 && s2 == 0 && s4 == 0 && s5 == 0) {
        _state = RobotState::FORWARD;
        _motor.goForward();
    }
    // 좌측 센서 감지 (끝 제외): 부드러운 좌회전
    else if ((s2 == 1 && s1 == 0)   || (s2 == 1 && s3 == 1))  {
        _state = RobotState::SOFT_LEFT;
        _motor.turnLeftSoft();
        delay(3);
    }
    // 우측 센서 감지 (끝 제외): 부드러운 우회전
    else if ((s4 == 1 && s5 == 0) || (s4 == 1 && s3 == 1)){
        _state = RobotState::SOFT_RIGHT;
        _motor.turnRightSoft();
        delay(3);
    }
    // 좌측 끝 센서 감지: 급격한 좌회전
    else if (s1 == 1) {
        _state = RobotState::HARD_LEFT;
        _motor.turnLeftHard();
        delay(3);
    }
    // 우측 끝 센서 감지: 급격한 우회전
    else if (s5 == 1) {
        _state = RobotState::HARD_RIGHT;
        _motor.turnRightHard();
        delay(3);
    }
    // 라인 이탈
    else {
        _state = RobotState::OUT_OF_LINE;
        _motor.stop();
    }
}

void LineFollower::followLineBackward(int s1, int s2, int s3, int s4, int s5) {
    static unsigned long lastLogMs = 0;
    const unsigned long LOG_INTERVAL_MS = 100;
    unsigned long now = millis();
    bool mayLog = (now - lastLogMs >= LOG_INTERVAL_MS);

    // 전진과 동일 논리: 라인 왼쪽(s2/s1)→후미 좌측, 라인 오른쪽(s4/s5)→후미 우측
    if ((s3 == 1 && s1 == 0 && s2 == 0 && s4 == 0 && s5 == 0) || (s3 == 1 && s1 == 1 && s2 == 1 && s4 == 1 && s5 == 1) || (s3 == 1 && s1 == 0 && s2 == 1 && s4 == 1 && s5 == 0))  {
        _motor.goBackward();
    } else if ((s2 == 1 && s3 == 1 ) || (s2 == 1 && s3 == 0)) {
        if (mayLog) { Serial.println("[후진] goBackwardLeftSoft"); lastLogMs = now; }
        _motor.goBackwardLeftSoft();
        delay(3);
    } else if ((s4 == 1 && s3 == 0) || (s4 == 1 && s3 == 1)){
        if (mayLog) { Serial.println("[후진] goBackwardRightSoft"); lastLogMs = now; }
        _motor.goBackwardRightSoft();
        delay(3);
    } else if (s1 == 1) {
        if (mayLog) { Serial.println("[후진] goBackwardLeftHard"); lastLogMs = now; }
        _motor.goBackwardLeftHard();
        delay(3);
    } else if (s5 == 1) {
        if (mayLog) { Serial.println("[후진] goBackwardRightHard"); lastLogMs = now; }
        _motor.goBackwardRightHard();
        delay(3);
    } else {
        _motor.goBackward();
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
