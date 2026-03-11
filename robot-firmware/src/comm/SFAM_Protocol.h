/**
 * SFAM_Protocol.h
 * ===============
 * SFAM Binary Protocol (PROTOCOL.md v1.0) - CRC16-CCITT, 패킷 조립
 * control-server tcp_robot_server 호환
 */
#ifndef SFAM_PROTOCOL_H
#define SFAM_PROTOCOL_H

#include <Arduino.h>

#define SFAM_SOF          0xAA
#define SFAM_PKT_HDR_SIZE 6
#define SFAM_MAX_PAYLOAD  64
#define SFAM_PKT_MAX      (SFAM_PKT_HDR_SIZE + SFAM_MAX_PAYLOAD + 2)

#define MSG_HEARTBEAT_REQ  0x01
#define MSG_HEARTBEAT_ACK  0x02
#define MSG_AGV_TELEMETRY  0x10
#define MSG_AGV_TASK_CMD   0x11
#define MSG_AGV_TASK_ACK   0x12
#define MSG_AGV_STATUS_RPT 0x13
#define MSG_AGV_EMERGENCY  0x14
#define MSG_RFID_EVENT     0x24

#define ID_SERVER   0x00
#define ID_AGV_R01  0x01

/**
 * CRC16-CCITT (Poly 0x1021, Init 0xFFFF)
 */
inline uint16_t sfam_crc16(const uint8_t* data, uint8_t len) {
    uint16_t crc = 0xFFFF;
    for (uint8_t i = 0; i < len; i++) {
        crc ^= ((uint16_t)data[i] << 8);
        for (uint8_t b = 0; b < 8; b++)
            crc = (crc & 0x8000) ? (crc << 1) ^ 0x1021 : (crc << 1);
    }
    return crc;
}

/**
 * SFAM 패킷 조립 (헤더+페이로드+CRC)
 * @param outBuf 출력 버퍼
 * @param msgType MSG_xxx
 * @param srcId  송신 ID (AGV: 0x01)
 * @param dstId  수신 ID (서버: 0x00)
 * @param seq   시퀀스 번호
 * @param payload 페이로드 (nullptr이면 길이 0)
 * @param payLen 페이로드 길이
 * @return 전체 패킷 길이
 */
inline uint8_t sfam_build_packet(uint8_t* outBuf, uint8_t msgType, uint8_t srcId, uint8_t dstId,
                                 uint8_t seq, const uint8_t* payload, uint8_t payLen) {
    if (payLen > SFAM_MAX_PAYLOAD) payLen = SFAM_MAX_PAYLOAD;
    outBuf[0] = SFAM_SOF;
    outBuf[1] = msgType;
    outBuf[2] = srcId;
    outBuf[3] = dstId;
    outBuf[4] = seq;
    outBuf[5] = payLen;
    if (payload && payLen > 0) {
        memcpy(outBuf + SFAM_PKT_HDR_SIZE, payload, payLen);
    }
    uint16_t crc = sfam_crc16(outBuf, SFAM_PKT_HDR_SIZE + payLen);
    outBuf[SFAM_PKT_HDR_SIZE + payLen] = (uint8_t)(crc >> 8);
    outBuf[SFAM_PKT_HDR_SIZE + payLen + 1] = (uint8_t)(crc & 0xFF);
    return SFAM_PKT_HDR_SIZE + payLen + 2;
}

#endif
