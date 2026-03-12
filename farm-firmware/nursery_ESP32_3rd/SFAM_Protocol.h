#ifndef SFAM_PROTOCOL_H
#define SFAM_PROTOCOL_H

#include <stdint.h>

// ─────────────────────────────────────────────────────────────
// 패킷 프로토콜 상수
// ─────────────────────────────────────────────────────────────
#define SOF                 0xAA
#define MAX_PAYLOAD         64
#define PKT_HDR_SIZE        6                              // 고정 헤더 크기
#define PKT_MAX_FULL        (PKT_HDR_SIZE + MAX_PAYLOAD + 2) // 74 bytes

// MSG_TYPE
#define MSG_HEARTBEAT_REQ   0x01
#define MSG_HEARTBEAT_ACK   0x02
#define MSG_AGV_TELEMETRY   0x10
#define MSG_AGV_TASK_CMD    0x11
#define MSG_AGV_TASK_ACK    0x12
#define MSG_AGV_STATUS_RPT  0x13
#define MSG_AGV_EMERGENCY   0x14
#define MSG_SENSOR_BATCH    0x20
#define MSG_ACTUATOR_CMD    0x21
#define MSG_ACTUATOR_ACK    0x22
#define MSG_CTRL_STATUS     0x23
#define MSG_DOCK_REQ        0x30
#define MSG_DOCK_ACK        0x31
#define MSG_ERROR_REPORT    0xF0
#define MSG_ACK             0xFE
#define MSG_NAK             0xFF

// Device ID
#define ID_SERVER           0x00
#define ID_AGV_BASE         0x01
#define ID_AGV_MAX          0x08
#define ID_CTRL_BASE        0x10
#define ID_CTRL_MAX         0x1F
#define ID_NODE_BASE        0x20
#define ID_NODE_MAX         0x5F
#define ID_BROADCAST        0xFF

// ─────────────────────────────────────────────────────────────
// 수신 상태 머신
// ─────────────────────────────────────────────────────────────
enum ProtocolRxState : uint8_t {
    S_WAIT_SOF,
    S_HEADER,
    S_PAYLOAD,
    S_CRC_HI,
    S_CRC_LO
};

struct ProtocolRxParser {
    ProtocolRxState state = S_WAIT_SOF;
    uint8_t buf[PKT_HDR_SIZE + MAX_PAYLOAD];
    uint8_t count = 0;
    uint8_t payLen = 0;
    uint8_t crcHi = 0;
};

// ─────────────────────────────────────────────────────────────
// CRC16-CCITT 유틸리티 함수
// ─────────────────────────────────────────────────────────────
inline uint16_t calcCRC16(const uint8_t* data, uint8_t len) {
    uint16_t crc = 0xFFFF;
    for (uint8_t i = 0; i < len; i++) {
        crc ^= ((uint16_t)data[i] << 8);
        for (uint8_t b = 0; b < 8; b++) {
            crc = (crc & 0x8000) ? (crc << 1) ^ 0x1021 : (crc << 1);
        }
    }
    return crc;
}

// 헤더+페이로드 버퍼를 받아 CRC를 추가하여 완성 패킷 생성
inline uint8_t makeFullPacket(const uint8_t* hdrPayBuf, uint8_t hdrPayLen, uint8_t* outBuf) {
    memcpy(outBuf, hdrPayBuf, hdrPayLen);
    uint16_t crc = calcCRC16(hdrPayBuf, hdrPayLen);
    outBuf[hdrPayLen]     = (uint8_t)(crc >> 8);   // Big-Endian MSB
    outBuf[hdrPayLen + 1] = (uint8_t)(crc & 0xFF); // Big-Endian LSB
    return hdrPayLen + 2;
}

#endif // SFAM_PROTOCOL_H
