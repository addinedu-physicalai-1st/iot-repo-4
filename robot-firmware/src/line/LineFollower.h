/**
 * LineFollower.h
 * ==============
 * ESP32 로봇 라인트레이싱 및 경로 추종 헤더 파일.
 *
 * 역할:
 *   - 5채널 IR 센서 기반 라인트레이싱
 *   - 교차로 감지 및 경로 명령 처리
 *   - 로봇 상태 관리
 */

#ifndef LINE_FOLLOWER_H
#define LINE_FOLLOWER_H

#include <Arduino.h>
#include "../motor/MotorController.h"

/**
 * @brief 로봇 주행 상태
 */
enum class RobotState {
    IDLE = 0,           // 대기
    FORWARD = 1,        // 직진
    SOFT_LEFT = 2,      // 부드러운 좌회전
    SOFT_RIGHT = 3,     // 부드러운 우회전
    HARD_LEFT = 4,      // 급격한 좌회전
    HARD_RIGHT = 5,     // 급격한 우회전
    CROSS_DETECTED = 6, // 교차로 인식 (정지)
    FINDING_LEFT = 7,   // 교차로에서 좌회전 진행 중
    FINDING_RIGHT = 8,  // 교차로에서 우회전 진행 중
    FINDING_UTURN = 9,  // 교차로에서 U턴 진행 중
    PASSING_STRAIGHT = 10, // 교차로 직진 통과
    ARRIVED = 11,       // 목적지 도착 완료
    OUT_OF_LINE = 12    // 라인 이탈 (정지)
};

/**
 * @brief 경로 명령 (숫자로 인코딩)
 */
enum class PathCommand {
    NONE = 0,
    LEFT = 1,       // L: 좌회전
    RIGHT = 2,      // R: 우회전
    UTURN = 3,      // U: U턴
    STRAIGHT = 4,   // S: 직진
    END = 5         // E: 종료
};

/**
 * @brief 라인트레이싱 및 경로 추종 클래스
 */
class LineFollower {
public:
    /**
     * @brief 생성자
     * @param motor MotorController 참조
     */
    explicit LineFollower(MotorController& motor);

    // ─────────── 경로 설정 ───────────

    /**
     * @brief 경로 설정.
     * @param path 숫자로 인코딩된 경로 문자열 (예: "12345")
     *             1=L, 2=R, 3=U, 4=S, 5=E
     */
    void setPath(const String& path);

    /**
     * @brief 주행 시작.
     */
    void start();

    /**
     * @brief 주행 정지.
     */
    void stop();

    // ─────────── 메인 루프 ───────────

    /**
     * @brief 매 loop() 사이클에서 호출.
     *        센서를 읽고 라인트레이싱/경로 추종 로직 실행.
     */
    void update();

    // ─────────── 상태 조회 ───────────

    /** @brief 현재 로봇 상태 반환 */
    RobotState getState() const { return _state; }

    /** @brief 현재 노드 이름 반환 (예: "A1", "A2") */
    String getCurrentNode() const { return _nodeName; }

    /** @brief 주행 중 여부 반환 */
    bool isRunning() const { return _isRunning; }

    /** @brief 현재 경로 진행 단계 반환 */
    int getCurrentStep() const { return _currentStep; }

    // ─────────── 센서 값 조회 ───────────

    /** @brief 센서 값 조회 (디버깅/상태 전송용) */
    void getSensorValues(int& s1, int& s2, int& s3, int& s4, int& s5) const;

private:
    // ─────────── 내부 로직 ───────────

    /** @brief 교차로 감지 여부 확인 */
    bool detectCrossroad(int s1, int s2, int s3, int s4, int s5);

    /** @brief 교차로에서 경로 명령 실행 */
    void executeCrossroadCommand();

    /** @brief 일반 라인트레이싱 수행 */
    void followLine(int s1, int s2, int s3, int s4, int s5);

    /** @brief 좌회전 완료 대기 (라인 안착) */
    void waitForLineAfterLeft();

    /** @brief 우회전 완료 대기 (라인 안착) */
    void waitForLineAfterRight();

    /** @brief U턴 완료 대기 (라인 안착) */
    void waitForLineAfterUturn();

    // ─────────── 멤버 변수 ───────────

    MotorController& _motor;    // 모터 컨트롤러 참조

    String _pathString;         // 경로 문자열 (숫자 인코딩)
    int _currentStep;           // 현재 경로 단계
    bool _isRunning;            // 주행 중 여부

    RobotState _state;          // 현재 로봇 상태
    String _nodeName;           // 현재 노드 이름

    // 센서 캐시 (상태 전송용)
    int _s1, _s2, _s3, _s4, _s5;
};

#endif // LINE_FOLLOWER_H
