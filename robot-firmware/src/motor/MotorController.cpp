/**
 * MotorController.cpp
 * ===================
 * ESP32 로봇 모터 및 센서 제어 구현 파일.
 */

#include "MotorController.h"

// ============================================================
//  생성자
// ============================================================

MotorController::MotorController()
    : _speedForward(200)
    , _speedSoft(200)
    , _speedHard(255)
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
//  모터 제어 함수
// ============================================================

void MotorController::goForward() {
    analogWrite(PIN_ENA, _speedForward);
    analogWrite(PIN_ENB, _speedForward);
    digitalWrite(PIN_IN1, HIGH);
    digitalWrite(PIN_IN2, LOW);
    digitalWrite(PIN_IN4, HIGH);
    digitalWrite(PIN_IN3, LOW);
}

void MotorController::turnLeftSoft() {
    analogWrite(PIN_ENA, _speedSoft);
    analogWrite(PIN_ENB, _speedSoft);
    digitalWrite(PIN_IN1, HIGH);
    digitalWrite(PIN_IN2, LOW);
    digitalWrite(PIN_IN4, LOW);
    digitalWrite(PIN_IN3, LOW);
}

void MotorController::turnRightSoft() {
    analogWrite(PIN_ENA, _speedSoft);
    analogWrite(PIN_ENB, _speedSoft);
    digitalWrite(PIN_IN1, LOW);
    digitalWrite(PIN_IN2, LOW);
    digitalWrite(PIN_IN4, HIGH);
    digitalWrite(PIN_IN3, LOW);
}

void MotorController::turnLeftHard() {
    analogWrite(PIN_ENA, _speedHard);
    analogWrite(PIN_ENB, _speedHard);
    digitalWrite(PIN_IN1, HIGH);
    digitalWrite(PIN_IN2, LOW);
    digitalWrite(PIN_IN4, LOW);
    digitalWrite(PIN_IN3, LOW);
}

void MotorController::turnRightHard() {
    analogWrite(PIN_ENA, _speedHard);
    analogWrite(PIN_ENB, _speedHard);
    digitalWrite(PIN_IN1, LOW);
    digitalWrite(PIN_IN2, LOW);
    digitalWrite(PIN_IN4, HIGH);
    digitalWrite(PIN_IN3, LOW);
}

void MotorController::uTurnRight() {
    analogWrite(PIN_ENA, _speedHard);
    analogWrite(PIN_ENB, _speedHard);
    digitalWrite(PIN_IN1, LOW);
    digitalWrite(PIN_IN2, HIGH);
    digitalWrite(PIN_IN4, HIGH);
    digitalWrite(PIN_IN3, LOW);
}

void MotorController::stop() {
    analogWrite(PIN_ENA, 0);
    analogWrite(PIN_ENB, 0);
    digitalWrite(PIN_IN1, LOW);
    digitalWrite(PIN_IN2, LOW);
    digitalWrite(PIN_IN3, LOW);
    digitalWrite(PIN_IN4, LOW);
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
