/**
 * MotorController.h
 * =================
 * ESP32 로봇 모터 및 센서 제어 헤더 파일.
 *
 * 역할:
 *   - DC 모터 제어 (L298N 드라이버)
 *   - IR 라인 센서 읽기 (5채널)
 *   - 속도 설정
 */

#ifndef MOTOR_CONTROLLER_H
#define MOTOR_CONTROLLER_H

#include <Arduino.h>

class MotorController {
public:
    MotorController();

    /**
     * @brief GPIO 핀 초기화.
     *        setup()에서 한 번 호출해야 함.
     */
    void init();

    // ─────────── 모터 제어 ───────────

    /** @brief 직진 */
    void goForward();

    /** @brief 부드러운 좌회전 (한쪽 바퀴만 구동) */
    void turnLeftSoft();

    /** @brief 부드러운 우회전 (한쪽 바퀴만 구동) */
    void turnRightSoft();

    /** @brief 급격한 좌회전 */
    void turnLeftHard();

    /** @brief 급격한 우회전 */
    void turnRightHard();

    /** @brief U턴 (제자리 우회전) */
    void uTurnRight();

    /** @brief 모터 정지 */
    void stop();

    // ─────────── 센서 읽기 ───────────

    /**
     * @brief 5개 IR 센서 값을 읽어 참조 변수에 저장.
     * @param s1 좌측 끝 센서
     * @param s2 좌측 센서
     * @param s3 중앙 센서
     * @param s4 우측 센서
     * @param s5 우측 끝 센서
     */
    void readSensors(int& s1, int& s2, int& s3, int& s4, int& s5);

    // ─────────── 속도 설정 ───────────

    /**
     * @brief 모터 속도 설정.
     * @param forward 직진 속도 (0-255)
     * @param soft    소프트 회전 속도 (0-255)
     * @param hard    하드 회전 속도 (0-255)
     */
    void setSpeed(int forward, int soft, int hard);

    // ─────────── 속도 조회 ───────────
    int getSpeedForward() const { return _speedForward; }
    int getSpeedSoft() const { return _speedSoft; }
    int getSpeedHard() const { return _speedHard; }

private:
    // ─────────── 모터 드라이버 핀 (L298N) ───────────
    static const int PIN_ENA = 14;  // 좌측 모터 PWM
    static const int PIN_IN1 = 27;  // 좌측 모터 방향 1
    static const int PIN_IN2 = 26;  // 좌측 모터 방향 2
    static const int PIN_IN3 = 25;  // 우측 모터 방향 1
    static const int PIN_IN4 = 32;  // 우측 모터 방향 2
    static const int PIN_ENB = 33;  // 우측 모터 PWM

    // ─────────── IR 센서 핀 ───────────
    static const int PIN_S1 = 18;   // 좌측 끝
    static const int PIN_S2 = 19;   // 좌측
    static const int PIN_S3 = 21;   // 중앙
    static const int PIN_S4 = 22;   // 우측
    static const int PIN_S5 = 23;   // 우측 끝

    // ─────────── 속도 설정 ───────────
    int _speedForward;
    int _speedSoft;
    int _speedHard;
};

#endif // MOTOR_CONTROLLER_H
