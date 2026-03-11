/**
 * MotorController.cpp
 * ===================
 * ESP32 로봇 모터 및 센서 제어 구현 파일.
 *
 * [모터 드라이버: L298N]
 *   - ENA, ENB: PWM으로 속도 제어 (0이면 모터 비활성화)
 *   - IN1, IN2: 좌측 모터 방향 (H/L)
 *   - IN3, IN4: 우측 모터 방향 (H/L)
 */

#include "MotorController.h"

// ============================================================
//  생성자
// ============================================================

MotorController::MotorController()
    : _speedForward(200)
    , _speedSoft(200)
    , _speedHard(210)
    , _speedSoftSlow(200)   // 부드러운 회전 시 느린 쪽 모터 속도
    , _speedBackwardSoftSlow(200)  // 후진 라인 추종 보정 시 느린 쪽 (80~120 조정)
{
}

// ============================================================
//  초기화
// ============================================================

void MotorController::init() {
    // 모터 드라이버 핀 설정
    pinMode(PIN_ENA, OUTPUT);
    pinMode(PIN_IN1, OUTPUT);
    pinMode(PIN_IN2, OUTPUT);
    pinMode(PIN_IN3, OUTPUT);
    pinMode(PIN_IN4, OUTPUT);
    pinMode(PIN_ENB, OUTPUT);

    // IR 센서 핀 설정
    pinMode(PIN_S1, INPUT);
    pinMode(PIN_S2, INPUT);
    pinMode(PIN_S3, INPUT);
    pinMode(PIN_S4, INPUT);
    pinMode(PIN_S5, INPUT);

    // 초기 상태: 정지
    stop();

    Serial.println("[MotorController] 초기화 완료");
}

// ============================================================
//  모터 제어 함수 (L9110S)
// ============================================================

void MotorController::goForward() {
    // L298N: IN1/IN2 방향, ENA 속도 | IN3/IN4 방향, ENB 속도
    digitalWrite(PIN_IN1, HIGH);
    digitalWrite(PIN_IN2, LOW);
    digitalWrite(PIN_IN3, HIGH);
    digitalWrite(PIN_IN4, LOW);
    analogWrite(PIN_ENA, _speedForward);
    analogWrite(PIN_ENB, _speedForward);
}

void MotorController::goBackward() {
    // 좌·우 모터 모두 후진
    digitalWrite(PIN_IN1, LOW);
    digitalWrite(PIN_IN2, HIGH);
    digitalWrite(PIN_IN3, LOW);
    digitalWrite(PIN_IN4, HIGH);
    analogWrite(PIN_ENA, _speedForward);
    analogWrite(PIN_ENB, _speedForward);
}

void MotorController::goBackwardLeftSoft() {
    // 후진 + 좌측 보정: 좌측만 후진 → 후미가 왼쪽으로 꺾임
    digitalWrite(PIN_IN1, LOW);
    digitalWrite(PIN_IN2, HIGH);  // 좌측 후진
    digitalWrite(PIN_IN3, LOW);
    digitalWrite(PIN_IN4, LOW);   // 우측 정지
    analogWrite(PIN_ENA, _speedSoft);
    analogWrite(PIN_ENB, 0);
}

void MotorController::goBackwardRightSoft() {
    // 후진 + 우측 보정: 우측만 후진 → 후미가 오른쪽으로 꺾임
    digitalWrite(PIN_IN1, LOW);
    digitalWrite(PIN_IN2, LOW);   // 좌측 정지
    digitalWrite(PIN_IN3, LOW);
    digitalWrite(PIN_IN4, HIGH);  // 우측 후진
    analogWrite(PIN_ENA, 0);
    analogWrite(PIN_ENB, _speedSoft);
}

void MotorController::goBackwardLeftHard() {
    // 후진 + 급격한 좌측 보정
    digitalWrite(PIN_IN1, LOW);
    digitalWrite(PIN_IN2, HIGH);
    digitalWrite(PIN_IN3, LOW);
    digitalWrite(PIN_IN4, HIGH);
    analogWrite(PIN_ENA, _speedBackwardSoftSlow);
    analogWrite(PIN_ENB, _speedHard);
}

void MotorController::goBackwardRightHard() {
    // 후진 + 급격한 우측 보정
    digitalWrite(PIN_IN1, LOW);
    digitalWrite(PIN_IN2, HIGH);
    digitalWrite(PIN_IN3, LOW);
    digitalWrite(PIN_IN4, HIGH);
    analogWrite(PIN_ENA, _speedHard);
    analogWrite(PIN_ENB, _speedBackwardSoftSlow);
}

void MotorController::turnLeftSoft() {
    // 우측만 빠르게, 좌측 정지 → 부드러운 좌회전 보정
    digitalWrite(PIN_IN1, LOW);   // 좌측 모터 정지
    digitalWrite(PIN_IN2, LOW);
    digitalWrite(PIN_IN3, HIGH);
    digitalWrite(PIN_IN4, LOW);
    analogWrite(PIN_ENA, 0);      // 좌측 모터 속도 0
    analogWrite(PIN_ENB, _speedSoft);
}

void MotorController::turnRightSoft() {
    // 좌측만 빠르게, 우측 정지 → 부드러운 우회전 보정
    digitalWrite(PIN_IN1, HIGH);
    digitalWrite(PIN_IN2, LOW);
    digitalWrite(PIN_IN3, LOW);   // 우측 모터 정지
    digitalWrite(PIN_IN4, LOW);
    analogWrite(PIN_ENA, _speedSoft);
    analogWrite(PIN_ENB, 0);      // 우측 모터 속도 0
}

void MotorController::turnLeftHard() {
    // 좌측 후진, 우측 전진 → 제자리 좌회전
    digitalWrite(PIN_IN1, LOW);
    digitalWrite(PIN_IN2, HIGH);
    digitalWrite(PIN_IN3, HIGH);
    digitalWrite(PIN_IN4, LOW);
    analogWrite(PIN_ENA, _speedHard);
    analogWrite(PIN_ENB, _speedHard);
}

void MotorController::turnRightHard() {
    // 좌측 전진, 우측 후진 → 제자리 우회전
    digitalWrite(PIN_IN1, HIGH);
    digitalWrite(PIN_IN2, LOW);
    digitalWrite(PIN_IN3, LOW);
    digitalWrite(PIN_IN4, HIGH);
    analogWrite(PIN_ENA, _speedHard);
    analogWrite(PIN_ENB, _speedHard);
}

void MotorController::uTurnRight() {
    // 우회전 U턴: 좌측 전진, 우측 후진
    digitalWrite(PIN_IN1, HIGH);
    digitalWrite(PIN_IN2, LOW);
    digitalWrite(PIN_IN3, LOW);
    digitalWrite(PIN_IN4, HIGH);
    analogWrite(PIN_ENA, _speedHard);
    analogWrite(PIN_ENB, _speedHard);
}

void MotorController::stop() {
    // L298N: ENA/ENB=0 이면 모터 비활성화
    digitalWrite(PIN_IN1, LOW);
    digitalWrite(PIN_IN2, LOW);
    digitalWrite(PIN_IN3, LOW);
    digitalWrite(PIN_IN4, LOW);
    analogWrite(PIN_ENA, 0);
    analogWrite(PIN_ENB, 0);
}

// ============================================================
//  센서 읽기
// ============================================================

void MotorController::readSensors(int& s1, int& s2, int& s3, int& s4, int& s5) {
    s1 = digitalRead(PIN_S1);
    s2 = digitalRead(PIN_S2);
    s3 = digitalRead(PIN_S3);
    s4 = digitalRead(PIN_S4);
    s5 = digitalRead(PIN_S5);
}

// ============================================================
//  속도 설정
// ============================================================

void MotorController::setSpeed(int forward, int soft, int hard) {
    _speedForward = constrain(forward, 0, 255);
    _speedSoft = constrain(soft, 0, 255);
    _speedHard = constrain(hard, 0, 255);
    Serial.printf("[MotorController] 속도 설정: FW=%d, Soft=%d, Hard=%d\n",
                  _speedForward, _speedSoft, _speedHard);
}
