/**
 * ============================================================
 *  SFAM Nursery Controller  v5.0
 *  Arduino Uno  ←→  ESP32  Binary Packet Protocol
 *  SFAM Serial Packet Spec v1.1 — TRAY_INFO_REQ/ACK 추가
 * ============================================================
 *
 *  [v4.0 → v5.0 변경]
 *  ● RFID Block 2 읽기 추가 → ref_id(tray_id) 추출          [수정]
 *  ● MSG_TRAY_INFO_REQ (0x25) 패킷 추가                      [신규]
 *  ● MSG_TRAY_INFO_ACK (0x26) 수신 처리 추가                 [신규]
 *  ● GrowthParam 구조체 + growthTable[] 추가                 [신규]
 *  ● applyTrayInfo() — 생육단계별 제어 파라미터 갱신          [신규]
 *  ● handleTrayInfoAck() — ACK 수신 디스패처                 [신규]
 *  ● printPacketInfo() — MSG_TYPE별 Payload 해석 출력        [신규]
 *  ● sendTrayInfoReq() — TRAY_INFO_REQ 패킷 송신             [신규]
 *  ● sendRfidEvent() — card_label 포함 출력                  [수정]
 *  ● checkRFID() — Block 2 읽기 추가                         [수정]
 *  ● handlePacket() — 0x26 케이스 추가                       [수정]
 *  ● 함수 섹션별 분리 정리
 *
 *  ─────────────────────────────────────────────────────────
 *  [전체 프로세스]
 *   ① RFID 카드 태그
 *   ② Block 0 → UID 읽기
 *   ③ Block 2 → ref_id(tray_id) 읽기
 *   ④ TRAY_INFO_REQ(0x25) → Host PC 전송
 *   ⑤ TRAY_INFO_ACK(0x26) 수신 → 품종/생육단계/수량 파싱
 *   ⑥ growthTable[] 참조 → 제어 파라미터 갱신
 *   ⑦ runAutoControl() → 갱신된 파라미터로 환경 제어
 *  ─────────────────────────────────────────────────────────
 *
 *  [핀 매핑]
 *   RGB LED PWM  : R=D3  G=D5  B=D6
 *   MOSFET       : 물펌프=D4  순환팬=D7  히터=D8
 *   RFID RC522   : RST=D9  SS=D10  MOSI=D11  MISO=D12  SCK=D13
 *   DHT22        : D2
 *   조도 센서     : A0
 *   수위 센서     : A1
 *   ESP32 Serial : TX=A2  RX=A3  @115,200bps
 *
 * ============================================================
 */

#include <SPI.h>
#include <MFRC522.h>
#include <DHT.h>
#include <SoftwareSerial.h>

// ─────────────────────────────────────────────────────────────
//  핀 정의
// ─────────────────────────────────────────────────────────────
#define PIN_LED_R     3
#define PIN_LED_G     5
#define PIN_LED_B     6
#define PIN_PUMP      4
#define PIN_FAN       7
#define PIN_HEATER    8
#define PIN_RFID_RST  9
#define PIN_RFID_SS   10
#define PIN_DHT       2
#define PIN_LUX       A0
#define PIN_WATER     A1
#define PIN_SW_TX     A2
#define PIN_SW_RX     A3

// ─────────────────────────────────────────────────────────────
//  시스템 상수
// ─────────────────────────────────────────────────────────────
#define DHT_TYPE          DHT22
#define BAUD_DEBUG        115200
#define BAUD_ESP32        115200

// 장치 ID
#define MY_ID             0x10
#define SERVER_ID         0x00
#define BROADCAST_ID      0xFF

// 패킷 프레임
#define SOF               0xAA
#define MAX_PAYLOAD       64

// ─────────────────────────────────────────────────────────────
//  MSG_TYPE 코드  (Packet Spec §2)
// ─────────────────────────────────────────────────────────────
#define MSG_HEARTBEAT_REQ 0x01
#define MSG_HEARTBEAT_ACK 0x02
#define MSG_SENSOR_BATCH  0x20
#define MSG_ACTUATOR_CMD  0x21
#define MSG_ACTUATOR_ACK  0x22
#define MSG_CTRL_STATUS   0x23
#define MSG_RFID_EVENT    0x24
#define MSG_TRAY_INFO_REQ 0x25    // [신규] Arduino → Server : tray_id 전송
#define MSG_TRAY_INFO_ACK 0x26    // [신규] Server → Arduino : 품종/생육/수량 수신
#define MSG_ERROR_REPORT  0xF0
#define MSG_ACK           0xFE
#define MSG_NAK           0xFF

// 센서 ID
#define SENSOR_TEMP       101
#define SENSOR_HUM        102
#define SENSOR_LUX        103
#define SENSOR_WATER      104

// 액추에이터 ID
#define ACT_PUMP          1
#define ACT_FAN           2
#define ACT_HEATER        3
#define ACT_LED_R         4
#define ACT_LED_G         5
#define ACT_LED_B         6
#define ACT_MODE_CTRL     0xFF

// 트리거 ID
#define TRIG_AUTO         1
#define TRIG_MANUAL       2

// 전송 주기
#define SENSOR_INTERVAL   5000UL
#define CTRL_RPT_INTERVAL 60000UL
#define DHT_READ_INTERVAL 2000UL

// TRAY_INFO_REQ 타임아웃
#define TRAY_REQ_TIMEOUT  3000UL  // [신규] 3초 내 ACK 없으면 기본값 유지

// Big-Endian 변환
#define HTONS(x) ((uint16_t)(((x) << 8) | ((x) >> 8)))
#define HTONL(x) ((uint32_t)(((x) >> 24) | (((x) >> 8) & 0xFF00) \
                  | (((x) << 8) & 0xFF0000) | ((x) << 24)))
                  
// ─────────────────────────────────────────────────────────────
//  환경 제어 히스테리시스 상수  (v6.0에서 DB 연동 예정)
// ─────────────────────────────────────────────────────────────
#define TEMP_HYSTERESIS   2.0f   // 온도 히스테리시스 (°C)
#define LUX_HYSTERESIS    50     // 조도 히스테리시스 (ADC)

// ─────────────────────────────────────────────────────────────
//  객체 생성
// ─────────────────────────────────────────────────────────────
MFRC522        rfid(PIN_RFID_SS, PIN_RFID_RST);
DHT            dht(PIN_DHT, DHT_TYPE);
SoftwareSerial espSerial(PIN_SW_RX, PIN_SW_TX);

// ═══════════════════════════════════════════════════════════
//  ■ 패킷 프레임 구조체  (Packet Spec §1)
// ═══════════════════════════════════════════════════════════
typedef struct __attribute__((packed)) {
  uint8_t sof;
  uint8_t msg_type;
  uint8_t src_id;
  uint8_t dst_id;
  uint8_t seq;
  uint8_t len;
} PktHeader;

// ═══════════════════════════════════════════════════════════
//  ■ Payload 구조체
// ═══════════════════════════════════════════════════════════

typedef struct __attribute__((packed)) {
  uint8_t status_id;
  uint8_t aux_value;
} PayHeartbeatAck;

typedef struct __attribute__((packed)) {
  uint8_t sensor_id;
  uint8_t value[3];
} SensorEntry;

typedef struct __attribute__((packed)) {
  uint8_t     sensor_count;
  SensorEntry entries[10];
} PaySensorBatch;

typedef struct __attribute__((packed)) {
  uint8_t actuator_id;
  uint8_t state_value;
  uint8_t trigger_id;
  uint8_t duration_sec;
} PayActuatorCmd;

typedef struct __attribute__((packed)) {
  uint8_t actuator_id;
  uint8_t state_value;
  uint8_t result;
} PayActuatorAck;

typedef struct __attribute__((packed)) {
  uint8_t control_mode;
  uint8_t device_status;
  uint8_t actuator_bitmask;
  uint8_t error_flags;
} PayCtrlStatusRpt;

typedef struct __attribute__((packed)) {
  uint8_t uid[7];
} PayRfidEvent;

// ── [신규] §5.5  TRAY_INFO_REQ (0x25) — 2 bytes ──────────
typedef struct __attribute__((packed)) {
  uint8_t tray_id_hi;   // tray_id 상위 바이트 (Big-Endian)
  uint8_t tray_id_lo;   // tray_id 하위 바이트
} PayTrayInfoReq;

// ── [신규] §5.6  TRAY_INFO_ACK (0x26) — 4 bytes ──────────
typedef struct __attribute__((packed)) {
  uint8_t tray_id_lo;    // tray_id 하위 바이트 (확인용)
  uint8_t variety_id;    // 품종 ID → seedling_varieties
  uint8_t growth_stage;  // 생육단계 1~6
  uint8_t current_qty;   // 현재 묘 수량
} PayTrayInfoAck;

typedef struct __attribute__((packed)) {
  uint8_t error_id_hi;
  uint8_t error_id_lo;
  uint8_t severity;
  uint8_t context;
} PayErrorReport;

typedef struct __attribute__((packed)) {
  uint8_t acked_type;
  uint8_t seq;
} PayAck;

typedef struct __attribute__((packed)) {
  uint8_t nacked_type;
  uint8_t seq;
  uint8_t reason;
} PayNak;

// ═══════════════════════════════════════════════════════════
//  ■ [신규] 생육단계별 환경 제어 파라미터 테이블
// ═══════════════════════════════════════════════════════════
typedef struct {
  float   tempDay;
  float   tempNight;
  int     luxDay;
  uint8_t stageId;
  const char* stageName;                  // ← const char* 로 변경
} GrowthParam;

// growth_stage: 1=SEEDING 2=GERMINATION 3=SEEDLING
//               4=TRANSPLANT 5=GROWING 6=HARVEST
const GrowthParam growthTable[] = {
  { 25.0f, 20.0f, 400, 1, "SEEDING"     },
  { 26.0f, 22.0f, 500, 2, "GERMINATION" },
  { 24.0f, 18.0f, 600, 3, "SEEDLING"    },
  { 22.0f, 16.0f, 700, 4, "TRANSPLANT"  },
  { 23.0f, 17.0f, 650, 5, "GROWING"     },
  { 21.0f, 15.0f, 750, 6, "HARVEST"     },
};
#define GROWTH_TABLE_SIZE 6

// ═══════════════════════════════════════════════════════════
//  전역 상태 변수
// ═══════════════════════════════════════════════════════════

// ── 액추에이터 상태 ────────────────────────────────────────
bool    pumpState    = false;
bool    fanState     = false;
bool    heaterState  = false;
uint8_t ledR = 0, ledG = 0, ledB = 0;

// ── 제어 모드 ──────────────────────────────────────────────
bool autoMode = false;

// ── 환경 제어 파라미터 (growthTable로 동적 갱신) ───────────
float         targetTempDay   = 25.0f;
float         targetTempNight = 18.0f;
int           targetLuxDay    = 600;
int           waterMinLevel   = 200;
unsigned long pumpInterval    = 3600000UL;
unsigned long pumpDuration    = 30000UL;

// ── 자동 제어 보조 변수 ────────────────────────────────────
bool          isDaytime       = true;
bool          isWatering      = false;
unsigned long lastPumpStartMs = 0;

// ── 센서 캐시 ─────────────────────────────────────────────
float cachedTemp  = NAN;
float cachedHum   = NAN;
int   cachedLux   = 0;
int   cachedWater = 0;

// ── 타이머 ────────────────────────────────────────────────
unsigned long lastDhtReadMs  = 0;
unsigned long lastSensorMs   = 0;
unsigned long lastCtrlRptMs  = 0;

// ── RFID 상태 ─────────────────────────────────────────────
uint8_t lastUID[7]         = {0};
uint8_t lastUIDSize        = 0;
bool    newUIDReady        = false;
char    lastCardLabel[17]  = {0};   // [신규] Block 2 ref_id 문자열
bool    blockReadOk        = false; // [신규] Block 2 읽기 성공 여부

// ── [신규] TRAY_INFO 상태 ─────────────────────────────────
uint16_t      currentTrayId      = 0;
uint8_t       currentVarietyId   = 0;
uint8_t       currentGrowthStage = 0;
uint8_t       currentQty         = 0;
bool          trayInfoPending    = false;   // REQ 후 ACK 대기 중
unsigned long trayReqSentMs      = 0;       // REQ 송신 시각

// ── SEQ ───────────────────────────────────────────────────
static uint8_t txSeq = 0;

// ── 수신 상태 머신 ────────────────────────────────────────
enum RxState { S_WAIT_SOF, S_HEADER, S_PAYLOAD, S_CRC_HI, S_CRC_LO };
RxState rxState  = S_WAIT_SOF;
uint8_t rxBuf[6 + MAX_PAYLOAD];
uint8_t rxCount  = 0;
uint8_t rxPayLen = 0;
uint8_t rxCrcHi  = 0;

// ─────────────────────────────────────────────────────────────
//  함수 선언
// ─────────────────────────────────────────────────────────────

// ── 유틸리티 ──────────────────────────────────────────────
uint16_t calcCRC16(const uint8_t* data, uint8_t len);
void     encodeInt24(uint8_t* out, long val);
void     printHex(uint8_t b);
void     printPacketInfo(uint8_t msgType, const uint8_t* pay, uint8_t payLen); // [신규]

// ── 패킷 송신 ─────────────────────────────────────────────
void     sendPacket(uint8_t msgType, uint8_t dstId, const void* payload, uint8_t len);
void     sendHeartbeatAck();
void     sendSensorBatch();
void     sendActuatorAck(uint8_t actId, uint8_t stateVal, uint8_t result);
void     sendCtrlStatusRpt();
void     sendRfidEvent();                                        // [수정]
void     sendTrayInfoReq(uint16_t trayId);                       // [신규]
void     sendErrorReport(uint16_t errorId, uint8_t severity, uint8_t context);
void     sendAck(uint8_t msgType, uint8_t seq);
void     sendNak(uint8_t msgType, uint8_t seq, uint8_t reason);

// ── 수신 처리 ─────────────────────────────────────────────
void     processRxByte(uint8_t b);
void     handlePacket(uint8_t msgType, uint8_t srcId, uint8_t seq,
                      const uint8_t* pay, uint8_t len);
void     handleActuatorCmd(uint8_t seq, const uint8_t* pay);
void     handleTrayInfoAck(uint8_t seq, const uint8_t* pay);     // [신규]

// ── 액추에이터 제어 ───────────────────────────────────────
void     applyActuator(uint8_t actId, uint8_t stateVal, uint8_t* result);
void     setPumpRaw(bool on);
void     setFanRaw(bool on);
void     setHeaterRaw(bool on);
void     setLedRaw(uint8_t r, uint8_t g, uint8_t b);

// ── 센서 / 자동제어 ───────────────────────────────────────
void     readSensors();
void     runAutoControl();
void     applyTrayInfo(uint8_t growthStage);                     // [신규]
void     checkTrayReqTimeout();                                  // [신규]

// ── RFID ──────────────────────────────────────────────────
void     checkRFID();                                            // [수정]
bool     readRfidBlock2(char* outLabel);                         // [신규]

// ── 디버그 ────────────────────────────────────────────────
void     debugPrintStatus();

// ═══════════════════════════════════════════════════════════
//  ■ 유틸리티 함수
// ═══════════════════════════════════════════════════════════

uint16_t calcCRC16(const uint8_t* data, uint8_t len) {
  uint16_t crc = 0xFFFF;
  for (uint8_t i = 0; i < len; i++) {
    crc ^= ((uint16_t)data[i] << 8);
    for (uint8_t b = 0; b < 8; b++)
      crc = (crc & 0x8000) ? (crc << 1) ^ 0x1021 : (crc << 1);
  }
  return crc;
}

void encodeInt24(uint8_t* out, long val) {
  val = constrain(val, -8388608L, 8388607L);
  out[0] = (uint8_t)((val >> 16) & 0xFF);
  out[1] = (uint8_t)((val >>  8) & 0xFF);
  out[2] = (uint8_t)( val        & 0xFF);
}

void printHex(uint8_t b) {
  if (b < 0x10) Serial.print('0');
  Serial.print(b, HEX);
}

// ─────────────────────────────────────────────────────────────
//  MSG_TYPE별 Payload 필드 해석 출력
// ─────────────────────────────────────────────────────────────
void printPacketInfo(uint8_t msgType, const uint8_t* pay, uint8_t payLen) {
  Serial.println(F("┌─── Payload Info ─────────────────────"));

  switch (msgType) {

    // ── 0x24  RFID_EVENT ─────────────────────────────────
    case MSG_RFID_EVENT:
      Serial.print(F("│ UID       : "));
      for (uint8_t i = 0; i < payLen; i++) {
        printHex(pay[i]);
        if (i < payLen - 1) Serial.print('-');
      }
      Serial.println();
      Serial.print(F("│ UID Size  : ")); Serial.print(payLen); Serial.println(F("B"));
      Serial.print(F("│ CardLabel : "));
      Serial.println(blockReadOk ? lastCardLabel
                                 : "읽기 실패 (미등록 또는 키 불일치)");
      break;

    // ── [신규] 0x25  TRAY_INFO_REQ ───────────────────────
    case MSG_TRAY_INFO_REQ: {
      uint16_t tid = ((uint16_t)pay[0] << 8) | pay[1];
      Serial.print(F("│ tray_id   : ")); Serial.println(tid);
      break;
    }

    // ── 0x20  SENSOR_BATCH ───────────────────────────────
    case MSG_SENSOR_BATCH: {
      uint8_t count = pay[0];
      Serial.print(F("│ Count     : ")); Serial.println(count);
      for (uint8_t i = 0; i < count; i++) {
        uint8_t sid = pay[1 + i * 4];
        long val = ((long)(int8_t)pay[2 + i*4] << 16)
                 | ((long)pay[3 + i*4] << 8)
                 |  (long)pay[4 + i*4];
        const __FlashStringHelper* name =
          sid == 101 ? F("Temp (°C) ") :
          sid == 102 ? F("Humid (%) ") :
          sid == 103 ? F("Lux (ADC) ") :
          sid == 104 ? F("Water(ADC)") : F("Unknown   ");
        Serial.print(F("│   [")); Serial.print(sid);
        Serial.print(F("] ")); Serial.print(name);
        Serial.print(F(" : "));
        Serial.print(val / 100); Serial.print('.');
        Serial.println(abs(val % 100));
      }
      break;
    }

    // ── 0x22  ACTUATOR_ACK ───────────────────────────────
    case MSG_ACTUATOR_ACK: {
      const char* actName =
        pay[0] == 1 ? "PUMP  " : pay[0] == 2 ? "FAN   " :
        pay[0] == 3 ? "HEATER" : pay[0] == 4 ? "LED-R " :
        pay[0] == 5 ? "LED-G " : pay[0] == 6 ? "LED-B " : "UNKNOWN";
      Serial.print(F("│ Actuator  : ")); Serial.print(pay[0]);
        Serial.print(F(" (")); Serial.print(actName); Serial.println(F(")"));
      Serial.print(F("│ State     : ")); Serial.print(pay[1]);
        Serial.println(pay[1] == 0 ? F(" (OFF)") :
                       pay[1] == 1 ? F(" (ON) ") : F(" (PWM)"));
      Serial.print(F("│ Result    : ")); Serial.print(pay[2]);
        Serial.println(pay[2] == 0 ? F(" (SUCCESS)") :
                       pay[2] == 1 ? F(" (FAIL)   ") : F(" (PARTIAL)"));
      break;
    }

    // ── 0x23  CTRL_STATUS_RPT ────────────────────────────
    case MSG_CTRL_STATUS:
      Serial.print(F("│ Mode      : "));
        Serial.println(pay[0] == 1 ? F("AUTO") : F("MANUAL"));
      Serial.print(F("│ Status    : "));
        Serial.println(pay[1] == 1 ? F("ONLINE") : F("OFFLINE"));
      Serial.print(F("│ Actuators : "));
        if (pay[2] & 0x01) Serial.print(F("PUMP "));
        if (pay[2] & 0x02) Serial.print(F("FAN "));
        if (pay[2] & 0x04) Serial.print(F("HEATER "));
        if (pay[2] & 0x08) Serial.print(F("LED-R "));
        if (pay[2] & 0x10) Serial.print(F("LED-G "));
        if (pay[2] & 0x20) Serial.print(F("LED-B "));
        if (pay[2] == 0)   Serial.print(F("ALL OFF"));
        Serial.println();
      Serial.print(F("│ Errors    : "));
        if (pay[3] == 0) Serial.println(F("NONE"));
        else {
          if (pay[3] & 0x01) Serial.print(F("SENSOR "));
          if (pay[3] & 0x02) Serial.print(F("ACTUATOR "));
          if (pay[3] & 0x04) Serial.print(F("COMM "));
          Serial.println();
        }
      break;

    // ── 0x02  HEARTBEAT_ACK ──────────────────────────────
    case MSG_HEARTBEAT_ACK:
      Serial.print(F("│ Status    : ")); Serial.println(pay[0]);
      Serial.print(F("│ Mode      : "));
        Serial.println(pay[1] == 1 ? F("AUTO") : F("MANUAL"));
      break;

    // ── 0xF0  ERROR_REPORT ───────────────────────────────
    case MSG_ERROR_REPORT: {
      uint16_t eid = ((uint16_t)pay[0] << 8) | pay[1];
      Serial.print(F("│ Error ID  : ")); Serial.println(eid);
      Serial.print(F("│ Severity  : "));
        Serial.println(pay[2] == 1 ? F("INFO") :
                       pay[2] == 2 ? F("WARN") : F("ERROR"));
      Serial.print(F("│ Context   : "));
        if (pay[3] & 0x01) Serial.print(F("작업중 "));
        if (pay[3] & 0x02) Serial.print(F("이동중 "));
        if (pay[3] & 0x04) Serial.print(F("도킹중 "));
        if (pay[3] & 0x08) Serial.print(F("수동모드 "));
        Serial.println();
      break;
    }

    // ── 0xFE  ACK ────────────────────────────────────────
    case MSG_ACK:
      Serial.print(F("│ Acked     : 0x")); printHex(pay[0]); Serial.println();
      Serial.print(F("│ Seq       : 0x")); printHex(pay[1]); Serial.println();
      break;

    // ── 0xFF  NAK ────────────────────────────────────────
    case MSG_NAK:
      Serial.print(F("│ Nacked    : 0x")); printHex(pay[0]); Serial.println();
      Serial.print(F("│ Seq       : 0x")); printHex(pay[1]); Serial.println();
      Serial.print(F("│ Reason    : "));
        Serial.println(pay[2] == 0 ? F("CRC 오류")  :
                       pay[2] == 1 ? F("LEN 오류")  :
                       pay[2] == 2 ? F("상태불가")  :
                       pay[2] == 3 ? F("권한없음")  : F("알 수 없음"));
      break;

    default:
      Serial.print(F("│ Raw       : "));
      for (uint8_t i = 0; i < payLen; i++) {
        printHex(pay[i]); Serial.print(' ');
      }
      Serial.println();
      break;
  }
  Serial.println(F("└─────────────────────────────────────"));
}

// ═══════════════════════════════════════════════════════════
//  ■ 패킷 송신 함수
// ═══════════════════════════════════════════════════════════

void sendPacket(uint8_t msgType, uint8_t dstId,
                const void* payload, uint8_t len) {
  if (len > MAX_PAYLOAD) return;
  uint8_t frame[6 + MAX_PAYLOAD + 2];
  PktHeader* hdr = (PktHeader*)frame;
  hdr->sof      = SOF;
  hdr->msg_type = msgType;
  hdr->src_id   = MY_ID;
  hdr->dst_id   = dstId;
  hdr->seq      = txSeq++;
  hdr->len      = len;
  if (len > 0) memcpy(frame + 6, payload, len);
  uint16_t crc = calcCRC16(frame, 6 + len);
  frame[6 + len]     = (uint8_t)(crc >> 8);
  frame[6 + len + 1] = (uint8_t)(crc & 0xFF);
  espSerial.write(frame, 6 + len + 2);
  Serial.print(F("[TX 0x")); printHex(msgType);
  Serial.print(F("] ")); Serial.print(6 + len + 2);
  Serial.print(F("B seq=0x")); printHex(hdr->seq);
  Serial.print(F(" | "));
  for (uint8_t i = 0; i < 6 + len + 2; i++) {
    printHex(frame[i]); Serial.print(' ');
  }
  Serial.println();
}

// ── 0x02  HEARTBEAT_ACK ──────────────────────────────────
void sendHeartbeatAck() {
  PayHeartbeatAck pay;
  pay.status_id = 0x01;
  pay.aux_value = autoMode ? 1 : 0;
  sendPacket(MSG_HEARTBEAT_ACK, SERVER_ID, &pay, sizeof(pay));
  printPacketInfo(MSG_HEARTBEAT_ACK, (const uint8_t*)&pay, sizeof(pay));
}

// ── 0x20  SENSOR_BATCH ───────────────────────────────────
void sendSensorBatch() {
  PaySensorBatch pay;
  pay.sensor_count = 4;
  pay.entries[0].sensor_id = SENSOR_TEMP;
  encodeInt24(pay.entries[0].value,
              isnan(cachedTemp) ? 0L : (long)(cachedTemp * 100.0f));
  pay.entries[1].sensor_id = SENSOR_HUM;
  encodeInt24(pay.entries[1].value,
              isnan(cachedHum) ? 0L : (long)(cachedHum * 100.0f));
  pay.entries[2].sensor_id = SENSOR_LUX;
  encodeInt24(pay.entries[2].value, (long)cachedLux * 100L);
  pay.entries[3].sensor_id = SENSOR_WATER;
  encodeInt24(pay.entries[3].value, (long)cachedWater * 100L);
  uint8_t payLen = 1 + pay.sensor_count * sizeof(SensorEntry);
  sendPacket(MSG_SENSOR_BATCH, SERVER_ID, &pay, payLen);
  printPacketInfo(MSG_SENSOR_BATCH, (const uint8_t*)&pay, payLen);
}

// ── 0x22  ACTUATOR_ACK ───────────────────────────────────
void sendActuatorAck(uint8_t actId, uint8_t stateVal, uint8_t result) {
  PayActuatorAck pay;
  pay.actuator_id = actId;
  pay.state_value = stateVal;
  pay.result      = result;
  sendPacket(MSG_ACTUATOR_ACK, SERVER_ID, &pay, sizeof(pay));
  printPacketInfo(MSG_ACTUATOR_ACK, (const uint8_t*)&pay, sizeof(pay));
}

// ── 0x23  CTRL_STATUS_RPT ────────────────────────────────
void sendCtrlStatusRpt() {
  PayCtrlStatusRpt pay;
  pay.control_mode     = autoMode ? 1 : 0;
  pay.device_status    = 0x01;
  pay.actuator_bitmask = 0;
  if (pumpState)   pay.actuator_bitmask |= (1 << 0);
  if (fanState)    pay.actuator_bitmask |= (1 << 1);
  if (heaterState) pay.actuator_bitmask |= (1 << 2);
  if (ledR > 0)    pay.actuator_bitmask |= (1 << 3);
  if (ledG > 0)    pay.actuator_bitmask |= (1 << 4);
  if (ledB > 0)    pay.actuator_bitmask |= (1 << 5);
  pay.error_flags = 0;
  if (isnan(cachedTemp) || isnan(cachedHum)) pay.error_flags |= 0x01;
  sendPacket(MSG_CTRL_STATUS, SERVER_ID, &pay, sizeof(pay));
  printPacketInfo(MSG_CTRL_STATUS, (const uint8_t*)&pay, sizeof(pay));
}

// ── 0x24  RFID_EVENT  [수정: card_label 출력 추가] ───────
void sendRfidEvent() {
  PayRfidEvent pay;
  memcpy(pay.uid, lastUID, lastUIDSize);
  sendPacket(MSG_RFID_EVENT, SERVER_ID, &pay, lastUIDSize);
  printPacketInfo(MSG_RFID_EVENT, (const uint8_t*)&pay, lastUIDSize);
}

// ── [신규] 0x25  TRAY_INFO_REQ ───────────────────────────
void sendTrayInfoReq(uint16_t trayId) {
  PayTrayInfoReq pay;
  pay.tray_id_hi = (uint8_t)(trayId >> 8);
  pay.tray_id_lo = (uint8_t)(trayId & 0xFF);
  sendPacket(MSG_TRAY_INFO_REQ, SERVER_ID, &pay, sizeof(pay));
  printPacketInfo(MSG_TRAY_INFO_REQ, (const uint8_t*)&pay, sizeof(pay));
  trayInfoPending = true;
  trayReqSentMs   = millis();
  Serial.print(F("[TRAY_REQ] tray_id=")); Serial.println(trayId);
}

// ── 0xF0  ERROR_REPORT ───────────────────────────────────
void sendErrorReport(uint16_t errorId, uint8_t severity, uint8_t context) {
  PayErrorReport pay;
  pay.error_id_hi = (uint8_t)(errorId >> 8);
  pay.error_id_lo = (uint8_t)(errorId & 0xFF);
  pay.severity    = severity;
  pay.context     = context;
  sendPacket(MSG_ERROR_REPORT, SERVER_ID, &pay, sizeof(pay));
  printPacketInfo(MSG_ERROR_REPORT, (const uint8_t*)&pay, sizeof(pay));
}

// ── 0xFE  ACK ────────────────────────────────────────────
void sendAck(uint8_t msgType, uint8_t seq) {
  PayAck pay;
  pay.acked_type = msgType;
  pay.seq        = seq;
  sendPacket(MSG_ACK, SERVER_ID, &pay, sizeof(pay));
}

// ── 0xFF  NAK ────────────────────────────────────────────
void sendNak(uint8_t msgType, uint8_t seq, uint8_t reason) {
  PayNak pay;
  pay.nacked_type = msgType;
  pay.seq         = seq;
  pay.reason      = reason;
  sendPacket(MSG_NAK, SERVER_ID, &pay, sizeof(pay));
}

// ═══════════════════════════════════════════════════════════
//  ■ 수신 상태 머신
// ═══════════════════════════════════════════════════════════
void processRxByte(uint8_t b) {
  switch (rxState) {
    case S_WAIT_SOF:
      if (b == SOF) { rxBuf[0] = b; rxCount = 1; rxState = S_HEADER; }
      break;
    case S_HEADER:
      rxBuf[rxCount++] = b;
      if (rxCount == 6) {
        rxPayLen = rxBuf[5];
        if (rxPayLen > MAX_PAYLOAD) {
          Serial.println(F("[RX ERR] LEN overflow"));
          rxState = S_WAIT_SOF; rxCount = 0;
        } else {
          rxState = (rxPayLen > 0) ? S_PAYLOAD : S_CRC_HI;
        }
      }
      break;
    case S_PAYLOAD:
      rxBuf[rxCount++] = b;
      if (rxCount == 6 + rxPayLen) rxState = S_CRC_HI;
      break;
    case S_CRC_HI:
      rxCrcHi = b; rxState = S_CRC_LO;
      break;
    case S_CRC_LO: {
      uint16_t rxCrc  = ((uint16_t)rxCrcHi << 8) | b;
      uint16_t calCrc = calcCRC16(rxBuf, 6 + rxPayLen);
      if (rxCrc == calCrc) {
        PktHeader* hdr = (PktHeader*)rxBuf;
        if (hdr->dst_id == MY_ID || hdr->dst_id == BROADCAST_ID)
          handlePacket(hdr->msg_type, hdr->src_id, hdr->seq,
                       rxBuf + 6, rxPayLen);
      } else {
        Serial.print(F("[RX ERR] CRC calc=0x")); Serial.print(calCrc, HEX);
        Serial.print(F(" rx=0x"));               Serial.println(rxCrc, HEX);
        sendNak(rxBuf[1], rxBuf[4], 0);
      }
      rxState = S_WAIT_SOF; rxCount = 0;
      break;
    }
  }
}

// ═══════════════════════════════════════════════════════════
//  ■ 패킷 디스패처  [수정: 0x26 케이스 추가]
// ═══════════════════════════════════════════════════════════
void handlePacket(uint8_t msgType, uint8_t srcId, uint8_t seq,
                  const uint8_t* pay, uint8_t len) {
  Serial.print(F("[RX 0x")); printHex(msgType);
  Serial.print(F("] src=0x")); printHex(srcId);
  Serial.print(F(" seq=")); Serial.println(seq);

  switch (msgType) {
    case MSG_HEARTBEAT_REQ:
      sendHeartbeatAck();
      break;
    case MSG_ACTUATOR_CMD:
      if (len == sizeof(PayActuatorCmd)) handleActuatorCmd(seq, pay);
      else { sendNak(msgType, seq, 1); Serial.println(F("[ERR] ACTUATOR_CMD bad len")); }
      break;
    case MSG_TRAY_INFO_ACK:                         // [신규]
      if (len == sizeof(PayTrayInfoAck)) handleTrayInfoAck(seq, pay);
      else { sendNak(msgType, seq, 1); Serial.println(F("[ERR] TRAY_INFO_ACK bad len")); }
      break;
    case MSG_ACK:
      Serial.println(F("[ACK received from server]"));
      break;
    default:
      sendNak(msgType, seq, 9);
      break;
  }
}

// ═══════════════════════════════════════════════════════════
//  ■ ACTUATOR_CMD 처리
// ═══════════════════════════════════════════════════════════
void handleActuatorCmd(uint8_t seq, const uint8_t* pay) {
  const PayActuatorCmd* cmd = (const PayActuatorCmd*)pay;
  Serial.print(F("[ACTUATOR_CMD] id=")); Serial.print(cmd->actuator_id);
  Serial.print(F(" val="));             Serial.print(cmd->state_value);
  Serial.print(F(" trig="));            Serial.print(cmd->trigger_id);
  Serial.print(F(" dur="));             Serial.println(cmd->duration_sec);
  if (cmd->actuator_id == ACT_MODE_CTRL) {
    autoMode = (cmd->state_value == 1);
    if (autoMode) { lastPumpStartMs = millis(); isWatering = false; }
    Serial.println(autoMode ? F("[MODE] AUTO") : F("[MODE] MANUAL"));
    sendActuatorAck(cmd->actuator_id, cmd->state_value, 0);
    sendAck(MSG_ACTUATOR_CMD, seq);
    return;
  }
  if (autoMode && cmd->trigger_id == TRIG_MANUAL) {
    sendActuatorAck(cmd->actuator_id, cmd->state_value, 1);
    sendNak(MSG_ACTUATOR_CMD, seq, 2);
    Serial.println(F("[WARN] AUTO 모드 중 수동 명령 거부"));
    return;
  }
  uint8_t result = 0;
  applyActuator(cmd->actuator_id, cmd->state_value, &result);
  sendActuatorAck(cmd->actuator_id, cmd->state_value, result);
  sendAck(MSG_ACTUATOR_CMD, seq);
}

// ═══════════════════════════════════════════════════════════
//  ■ [신규] TRAY_INFO_ACK 처리
//  수신된 품종/생육단계/수량으로 제어 파라미터 갱신
// ═══════════════════════════════════════════════════════════
void handleTrayInfoAck(uint8_t seq, const uint8_t* pay) {
  const PayTrayInfoAck* ack = (const PayTrayInfoAck*)pay;

  currentVarietyId   = ack->variety_id;
  currentGrowthStage = ack->growth_stage;
  currentQty         = ack->current_qty;
  trayInfoPending    = false;

  Serial.println(F("[TRAY_INFO_ACK] 수신"));
  Serial.print(F("  tray_id      : ")); Serial.println(currentTrayId);
  Serial.print(F("  variety_id   : ")); Serial.println(currentVarietyId);
  Serial.print(F("  growth_stage : ")); Serial.println(currentGrowthStage);
  Serial.print(F("  current_qty  : ")); Serial.println(currentQty);

  // 생육단계 기반 제어 파라미터 적용
  applyTrayInfo(currentGrowthStage);
  sendAck(MSG_TRAY_INFO_ACK, seq);
}

// ═══════════════════════════════════════════════════════════
//  ■ [신규] 생육단계별 제어 파라미터 갱신
// ═══════════════════════════════════════════════════════════
void applyTrayInfo(uint8_t growthStage) {
  if (growthStage < 1 || growthStage > GROWTH_TABLE_SIZE) {
    Serial.print(F("[WARN] 알 수 없는 생육단계=")); Serial.println(growthStage);
    return;
  }
  uint8_t idx = growthStage - 1;
  targetTempDay   = growthTable[idx].tempDay;
  targetTempNight = growthTable[idx].tempNight;
  targetLuxDay    = growthTable[idx].luxDay;

  Serial.print(F("[TRAY] 생육단계 적용: "));
  Serial.println(growthTable[idx].stageName);
  Serial.print(F("  TempDay="));   Serial.print(targetTempDay, 1);
  Serial.print(F("°C  TempNight=")); Serial.print(targetTempNight, 1);
  Serial.print(F("°C  Lux="));     Serial.println(targetLuxDay);
}

// ═══════════════════════════════════════════════════════════
//  ■ [신규] TRAY_INFO_REQ 타임아웃 체크
//  ACK 미수신 시 경고 출력 후 기본 파라미터 유지
// ═══════════════════════════════════════════════════════════
void checkTrayReqTimeout() {
  if (!trayInfoPending) return;
  if (millis() - trayReqSentMs >= TRAY_REQ_TIMEOUT) {
    trayInfoPending = false;
    Serial.println(F("[WARN] TRAY_INFO_ACK 타임아웃 — 기본 파라미터 유지"));
    sendErrorReport(300, 2, 0x04);  // error_id=300, WARN, 통신이상
  }
}

// ═══════════════════════════════════════════════════════════
//  ■ 액추에이터 제어 함수
// ═══════════════════════════════════════════════════════════
void applyActuator(uint8_t actId, uint8_t stateVal, uint8_t* result) {
  *result = 0;
  switch (actId) {
    case ACT_PUMP:   setPumpRaw(stateVal != 0);   break;
    case ACT_FAN:    setFanRaw(stateVal != 0);    break;
    case ACT_HEATER: setHeaterRaw(stateVal != 0); break;
    case ACT_LED_R:
      ledR = (stateVal == 1) ? 255 : stateVal;
      analogWrite(PIN_LED_R, ledR); break;
    case ACT_LED_G:
      ledG = (stateVal == 1) ? 255 : stateVal;
      analogWrite(PIN_LED_G, ledG); break;
    case ACT_LED_B:
      ledB = (stateVal == 1) ? 255 : stateVal;
      analogWrite(PIN_LED_B, ledB); break;
    default:
      Serial.print(F("[ERR] Unknown actuator id=")); Serial.println(actId);
      *result = 1; return;
  }
  Serial.print(F("[ACT] id=")); Serial.print(actId);
  Serial.print(F(" val="));    Serial.println(stateVal);
}

void setPumpRaw(bool on)   { pumpState   = on; digitalWrite(PIN_PUMP,   on ? HIGH : LOW); }
void setFanRaw(bool on)    { fanState    = on; digitalWrite(PIN_FAN,    on ? HIGH : LOW); }
void setHeaterRaw(bool on) { heaterState = on; digitalWrite(PIN_HEATER, on ? HIGH : LOW); }
void setLedRaw(uint8_t r, uint8_t g, uint8_t b) {
  ledR = r; ledG = g; ledB = b;
  analogWrite(PIN_LED_R, r);
  analogWrite(PIN_LED_G, g);
  analogWrite(PIN_LED_B, b);
}

// ═══════════════════════════════════════════════════════════
//  ■ 센서 읽기
// ═══════════════════════════════════════════════════════════
void readSensors() {
  unsigned long now = millis();
  if (now - lastDhtReadMs >= DHT_READ_INTERVAL) {
    lastDhtReadMs = now;
    float t = dht.readTemperature();
    float h = dht.readHumidity();
    if (!isnan(t)) cachedTemp = t;
    if (!isnan(h)) cachedHum  = h;
    if (isnan(t) || isnan(h)) {
      Serial.println(F("[ERR] DHT22 읽기 실패"));
      sendErrorReport(100, 2, 0x01);
    }
  }
  cachedLux   = analogRead(PIN_LUX);
  cachedWater = analogRead(PIN_WATER);
}

// ═══════════════════════════════════════════════════════════
//  ■ 자동 제어 로직
//  growthTable 기반 갱신된 파라미터로 동작
// ═══════════════════════════════════════════════════════════
void runAutoControl() {
  if (isnan(cachedTemp)) return;
  isDaytime = (cachedLux > 300);
  float target = isDaytime ? targetTempDay : targetTempNight;
  if (cachedTemp < target - TEMP_HYSTERESIS) setHeaterRaw(true);
  if (cachedTemp >= target)                   setHeaterRaw(false);
  if (cachedTemp > target + TEMP_HYSTERESIS) setFanRaw(true);
  if (cachedTemp <= target)                   setFanRaw(false);
  if (isDaytime && cachedLux < targetLuxDay) setLedRaw(255, 150, 100);
  else                                        setLedRaw(0, 0, 0);
  unsigned long now = millis();
  if (cachedWater > waterMinLevel) {
    if (!isWatering && (now - lastPumpStartMs >= pumpInterval)) {
      isWatering = true; lastPumpStartMs = now;
      setPumpRaw(true);
      Serial.println(F("[AUTO] 물 공급 시작"));
    }
    if (isWatering && (now - lastPumpStartMs >= pumpDuration)) {
      isWatering = false; setPumpRaw(false);
      Serial.println(F("[AUTO] 물 공급 완료"));
    }
  } else if (pumpState) {
    setPumpRaw(false); isWatering = false;
    sendErrorReport(200, 2, 0x01);
    Serial.println(F("[WARN] 수위 부족! 펌프 강제 정지"));
  }
}

// ═══════════════════════════════════════════════════════════
//  ■ RFID 함수
// ═══════════════════════════════════════════════════════════

// ── [신규] Block 2 읽기 → ref_id(tray_id) 추출 ──────────
bool readRfidBlock2(char* outLabel) {
  MFRC522::MIFARE_Key key;
  for (byte i = 0; i < 6; i++) key.keyByte[i] = 0xFF;   // 기본 인증키

  MFRC522::StatusCode status = rfid.PCD_Authenticate(
    MFRC522::PICC_CMD_MF_AUTH_KEY_A, 2, &key, &(rfid.uid));

  if (status != MFRC522::STATUS_OK) {
    Serial.print(F("[RFID] Block2 인증 실패: "));
    Serial.println(rfid.GetStatusCodeName(status));
    return false;
  }

  byte buf[18];
  byte bufSize = sizeof(buf);
  status = rfid.MIFARE_Read(2, buf, &bufSize);

  if (status != MFRC522::STATUS_OK) {
    Serial.print(F("[RFID] Block2 읽기 실패: "));
    Serial.println(rfid.GetStatusCodeName(status));
    return false;
  }

  memcpy(outLabel, buf, 16);
  outLabel[16] = '\0';
  return true;
}

// ── [수정] checkRFID — Block 2 읽기 + TRAY_INFO_REQ 자동 발송 ──
void checkRFID() {
  if (!rfid.PICC_IsNewCardPresent()) return;
  if (!rfid.PICC_ReadCardSerial())   return;

  // ① UID 저장
  lastUIDSize = rfid.uid.size;
  memcpy(lastUID, rfid.uid.uidByte, lastUIDSize);

  // ② Block 2 읽기 → ref_id 추출
  blockReadOk = readRfidBlock2(lastCardLabel);

  if (blockReadOk) {
    // card_label 형식: "TRAY-031", "NODE-A1-001", "WORKER-101"
    Serial.print(F("[RFID] CardLabel=")); Serial.println(lastCardLabel);

    // TRAY 카드인 경우 tray_id 파싱 후 TRAY_INFO_REQ 전송
    // card_label 형식: "TRAY-NNN"
    if (strncmp(lastCardLabel, "TRAY-", 5) == 0) {
      uint16_t trayId = (uint16_t)atoi(lastCardLabel + 5);
      if (trayId > 0) {
        currentTrayId = trayId;
        sendTrayInfoReq(trayId);   // ③ Host PC에 트레이 정보 요청
      }
    }
  }

  newUIDReady = true;
  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();
}

// ═══════════════════════════════════════════════════════════
//  ■ setup()
// ═══════════════════════════════════════════════════════════
void setup() {
  Serial.begin(BAUD_DEBUG);
  Serial.println(F("=== SFAM Nursery Controller v5.0 ==="));
  Serial.println(F("    TRAY_INFO_REQ/ACK + Block2 RFID"));

  espSerial.begin(BAUD_ESP32);

  pinMode(PIN_PUMP,   OUTPUT); digitalWrite(PIN_PUMP,   LOW);
  pinMode(PIN_FAN,    OUTPUT); digitalWrite(PIN_FAN,    LOW);
  pinMode(PIN_HEATER, OUTPUT); digitalWrite(PIN_HEATER, LOW);
  pinMode(PIN_LED_R,  OUTPUT); analogWrite(PIN_LED_R, 0);
  pinMode(PIN_LED_G,  OUTPUT); analogWrite(PIN_LED_G, 0);
  pinMode(PIN_LED_B,  OUTPUT); analogWrite(PIN_LED_B, 0);

  dht.begin();
  delay(2000);

  SPI.begin();
  rfid.PCD_Init();
  rfid.PCD_DumpVersionToSerial();

  readSensors();

  analogWrite(PIN_LED_B, 150); ledB = 150;
  delay(500);
  analogWrite(PIN_LED_B, 0);   ledB = 0;

  unsigned long now = millis();
  lastPumpStartMs = now;
  lastSensorMs    = now;
  lastCtrlRptMs   = now;

  Serial.println(F("[READY] 부팅 완료 | 'S' → STATUS"));
}

// ═══════════════════════════════════════════════════════════
//  ■ loop()
// ═══════════════════════════════════════════════════════════
void loop() {
  // 1) ESP32 수신
  while (espSerial.available())
    processRxByte((uint8_t)espSerial.read());

  // 2) RFID 감지 → RFID_EVENT + TRAY_INFO_REQ
  checkRFID();
  if (newUIDReady) { newUIDReady = false; sendRfidEvent(); }

  // 3) TRAY_INFO_REQ 타임아웃 체크  [신규]
  checkTrayReqTimeout();

  // 4) 센서 읽기
  readSensors();

  // 5) 자동 제어 (갱신된 growthTable 파라미터 적용)
  if (autoMode) runAutoControl();

  unsigned long now = millis();

  // 6) SENSOR_BATCH 5초 주기
  if (now - lastSensorMs >= SENSOR_INTERVAL) {
    lastSensorMs = now; sendSensorBatch();
  }

  // 7) CTRL_STATUS_RPT 60초 주기
  if (now - lastCtrlRptMs >= CTRL_RPT_INTERVAL) {
    lastCtrlRptMs = now; sendCtrlStatusRpt();
  }

  // 8) USB 디버그 'S'
  if (Serial.available()) {
    char c = (char)Serial.read();
    if (c == 'S' || c == 's') debugPrintStatus();
  }
}

// ═══════════════════════════════════════════════════════════
//  ■ 디버그 상태 출력
// ═══════════════════════════════════════════════════════════
void debugPrintStatus() {
  Serial.println(F("========== STATUS =========="));
  Serial.print(F("MODE       : ")); Serial.println(autoMode    ? F("AUTO")   : F("MANUAL"));
  Serial.print(F("PUMP       : ")); Serial.println(pumpState   ? F("ON")     : F("OFF"));
  Serial.print(F("FAN        : ")); Serial.println(fanState    ? F("ON")     : F("OFF"));
  Serial.print(F("HEATER     : ")); Serial.println(heaterState ? F("ON")     : F("OFF"));
  Serial.print(F("LED R/G/B  : "));
  Serial.print(ledR); Serial.print('/');
  Serial.print(ledG); Serial.print('/'); Serial.println(ledB);
  Serial.print(F("Daytime    : ")); Serial.println(isDaytime   ? F("YES")    : F("NO"));
  Serial.print(F("Watering   : ")); Serial.println(isWatering  ? F("YES")    : F("NO"));
  Serial.println(F("------- Sensor -------"));
  Serial.print(F("Temp       : ")); Serial.print(cachedTemp, 1); Serial.println(F(" C"));
  Serial.print(F("Humidity   : ")); Serial.print(cachedHum,  1); Serial.println(F(" %"));
  Serial.print(F("Lux(ADC)   : ")); Serial.println(cachedLux);
  Serial.print(F("Water ADC  : ")); Serial.println(cachedWater);
  Serial.println(F("------- TRAY INFO ----"));
  Serial.print(F("tray_id    : ")); Serial.println(currentTrayId);
  Serial.print(F("variety_id : ")); Serial.println(currentVarietyId);
  Serial.print(F("growth_stg : ")); Serial.println(currentGrowthStage);
  Serial.print(F("current_qty: ")); Serial.println(currentQty);
  Serial.print(F("TempDay    : ")); Serial.println(targetTempDay, 1);
  Serial.print(F("TempNight  : ")); Serial.println(targetTempNight, 1);
  Serial.print(F("LuxDay     : ")); Serial.println(targetLuxDay);
  Serial.println(F("------- RFID ---------"));
  Serial.print(F("LastUID    : "));
  for (uint8_t i = 0; i < lastUIDSize; i++) printHex(lastUID[i]);
  Serial.println();
  Serial.print(F("CardLabel  : ")); Serial.println(lastCardLabel);
  Serial.print(F("BlockReadOK: ")); Serial.println(blockReadOk ? F("YES") : F("NO"));
  Serial.println(F("============================"));
}
