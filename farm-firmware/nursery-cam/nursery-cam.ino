/**
 * ============================================================
 *  SFAM ESP32-CAM  UDP 영상 스트리밍  v2.0
 *  AI-Thinker ESP32-CAM Module
 * ============================================================
 *
 *  ● CAM_DEVICE_ID 추가 — UDP 패킷 헤더 첫 바이트에 포함
 *  ● 섹션별 Device ID 범위 정의
 *    · A 섹션 Nursery : 10 ~ 19  (CAM_SECTION = 'A')
 *    · B 섹션 Nursery : 20 ~ 29  (CAM_SECTION = 'B')
 *  ● UdpFrameHeader 구조체 도입 — 헤더 필드 명시적 관리
 *    · [cam_id(1B)] [frame_no(1B)] [packet_no(1B)] [checksum(1B)]
 *  ● 부팅 시 USB 시리얼에 섹션/ID 정보 출력
 *
 *  ─────────────────────────────────────────────────────────
 *  ★ 장치 설치 시 반드시 설정
 *     CAM_SECTION   : 설치 섹션  ('A' 또는 'B')
 *     CAM_DEVICE_ID : 해당 섹션 내 고유 번호
 *       A섹션 → 10~19 중 하나
 *       B섹션 → 20~29 중 하나
 *  ─────────────────────────────────────────────────────────
 *
 *  [UDP 패킷 구조 — 청크 단위]
 *   Offset  Size  Field
 *   0x00     1B   cam_id      ← 장치 고유 ID (10~29)
 *   0x01     1B   frame_no    ← 프레임 순번 (0~255 롤오버)
 *   0x02     1B   packet_no   ← 청크 순번 (프레임 내)
 *   0x03     1B   checksum    ← 마지막 청크: 전체 합산 체크섬
 *                                일반 청크: 0x00
 *   0x04    ~1024B JPEG data  ← 이미지 데이터 청크
 *
 *  [수신 측 식별 방법]
 *   UDP payload[0] == cam_id 로 카메라 구분
 *   payload[3] != 0  → 마지막 청크 (체크섬 포함)
 *
 *  [카메라 설정]
 *   해상도 : QVGA (320×240)
 *   품질   : JPEG quality 10
 *   프레임 : 10 FPS (100ms 간격)
 *   버퍼   : 3중 프레임 버퍼 (CAMERA_GRAB_LATEST)
 *
 * ============================================================
 */

#include "esp_camera.h"
#include <WiFi.h>
#include <WiFiUdp.h>

// ─────────────────────────────────────────────────────────────
//  ★ 장치별 설정 — 설치 전 반드시 수정
// ─────────────────────────────────────────────────────────────

// 설치 섹션 : 'A' 또는 'B'
#define CAM_SECTION       'A'

// 장치 ID : A섹션(10~19) / B섹션(20~29) 중 해당 번호 입력
#define CAM_DEVICE_ID      10

// ─────────────────────────────────────────────────────────────
//  섹션 / ID 유효성 검사 (컴파일 타임)
// ─────────────────────────────────────────────────────────────
#if CAM_SECTION == 'A'
  #if CAM_DEVICE_ID < 10 || CAM_DEVICE_ID > 19
    #error "A 섹션 CAM_DEVICE_ID 범위 오류 — 10~19 사이 값을 입력하세요."
  #endif
#elif CAM_SECTION == 'B'
  #if CAM_DEVICE_ID < 20 || CAM_DEVICE_ID > 29
    #error "B 섹션 CAM_DEVICE_ID 범위 오류 — 20~29 사이 값을 입력하세요."
  #endif
#else
  #error "CAM_SECTION은 'A' 또는 'B' 만 허용됩니다."
#endif

// ─────────────────────────────────────────────────────────────
//  섹션별 Device ID 범위 참조표 (주석용)
// ─────────────────────────────────────────────────────────────
// ┌────────────┬───────────┬──────────────────────────────┐
// │  섹션      │  ID 범위  │  비고                        │
// ├────────────┼───────────┼──────────────────────────────┤
// │ A Nursery  │  10 ~ 19  │  최대 10대 ESP32-CAM         │
// │ B Nursery  │  20 ~ 29  │  최대 10대 ESP32-CAM         │
// └────────────┴───────────┴──────────────────────────────┘

// ─────────────────────────────────────────────────────────────
//  네트워크 설정
// ─────────────────────────────────────────────────────────────
const char*  ssid       = "addinedu_201class_4-2.4G";
const char*  password   = "201class4!";
const char*  udpAddress = "192.168.0.135";   // Host PC IP
const int    udpPort    = 7070;

WiFiUDP udp;

// ─────────────────────────────────────────────────────────────
//  UDP 패킷 헤더 구조체  (4 bytes 고정)
// ─────────────────────────────────────────────────────────────
typedef struct __attribute__((packed)) {
  uint8_t cam_id;      // 장치 고유 ID (10~29)
  uint8_t frame_no;    // 프레임 순번 (0~255 롤오버)
  uint8_t packet_no;   // 프레임 내 청크 순번
  uint8_t checksum;    // 마지막 청크: 전체 JPEG 합산 / 일반: 0x00
} UdpFrameHeader;      // 4 bytes

// ─────────────────────────────────────────────────────────────
//  AI-Thinker ESP32-CAM 핀 맵핑
// ─────────────────────────────────────────────────────────────
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

// ═══════════════════════════════════════════════════════════
//  setup()
// ═══════════════════════════════════════════════════════════
void setup() {
  Serial.begin(115200);
  Serial.println();
  Serial.println("╔══════════════════════════════════════════╗");
  Serial.println("║  SFAM ESP32-CAM Streaming  v2.0          ║");
  Serial.println("╚══════════════════════════════════════════╝");
  Serial.printf("  섹션     : %c Nursery\n", CAM_SECTION);
  Serial.printf("  Device ID: %d\n", CAM_DEVICE_ID);
  Serial.println("────────────────────────────────────────────");

  // ── 카메라 초기화 ────────────────────────────────────────
  camera_config_t config;
  config.ledc_channel  = LEDC_CHANNEL_0;
  config.ledc_timer    = LEDC_TIMER_0;
  config.pin_d0        = Y2_GPIO_NUM;
  config.pin_d1        = Y3_GPIO_NUM;
  config.pin_d2        = Y4_GPIO_NUM;
  config.pin_d3        = Y5_GPIO_NUM;
  config.pin_d4        = Y6_GPIO_NUM;
  config.pin_d5        = Y7_GPIO_NUM;
  config.pin_d6        = Y8_GPIO_NUM;
  config.pin_d7        = Y9_GPIO_NUM;
  config.pin_xclk      = XCLK_GPIO_NUM;
  config.pin_pclk      = PCLK_GPIO_NUM;
  config.pin_vsync     = VSYNC_GPIO_NUM;
  config.pin_href      = HREF_GPIO_NUM;
  config.pin_sscb_sda  = SIOD_GPIO_NUM;
  config.pin_sscb_scl  = SIOC_GPIO_NUM;
  config.pin_pwdn      = PWDN_GPIO_NUM;
  config.pin_reset     = RESET_GPIO_NUM;
  config.xclk_freq_hz  = 10000000;
  config.pixel_format  = PIXFORMAT_JPEG;
  config.frame_size    = FRAMESIZE_QVGA;
  config.jpeg_quality  = 10;              // 10~12 권장
  config.fb_count      = 3;              // 3중 버퍼 (안정성 핵심)
  config.grab_mode     = CAMERA_GRAB_LATEST;

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("[CAM] 초기화 실패: 0x%x\n", err);
    delay(1000);
    ESP.restart();
  }
  Serial.println("[CAM] 초기화 완료");

  // ── WiFi 연결 ────────────────────────────────────────────
  WiFi.begin(ssid, password);
  WiFi.setSleep(false);   // 스트리밍 끊김 방지
  Serial.print("[WiFi] Connecting");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500); Serial.print('.');
  }
  Serial.printf("\n[WiFi] 연결 완료  IP=%s\n",
                WiFi.localIP().toString().c_str());
  Serial.printf("[UDP]  → %s:%d\n", udpAddress, udpPort);
  Serial.printf("[READY] CAM-ID=%d (%c 섹션) 스트리밍 시작\n",
                CAM_DEVICE_ID, CAM_SECTION);
  Serial.println("────────────────────────────────────────────");
}

// ═══════════════════════════════════════════════════════════
//  sendImageUDP()
//  JPEG 이미지를 1024B 청크 단위로 분할 전송
//
//  패킷 헤더 (4 bytes):
//   [cam_id] [frame_no] [packet_no] [checksum or 0x00]
//
//  ※ checksum: 마지막 청크에만 기록 (전체 JPEG 바이트 합산)
//               일반 청크는 0x00 (자릿수 유지)
// ═══════════════════════════════════════════════════════════
void sendImageUDP(uint8_t* imageData, size_t imageSize, uint8_t frameNo)
{
  const size_t CHUNK_SIZE = 1024;

  // ── 전체 JPEG 체크섬 계산 (단순 합산) ─────────────────────
  uint8_t checksum = 0;
  for (size_t i = 0; i < imageSize; i++)
    checksum += imageData[i];

  size_t  remaining = imageSize;
  uint8_t packetNo  = 0;

  while (remaining > 0) {
    size_t  chunkSize    = (remaining > CHUNK_SIZE) ? CHUNK_SIZE : remaining;
    bool    isLastPacket = (remaining <= CHUNK_SIZE);

    // ── 헤더 조립 ─────────────────────────────────────────
    UdpFrameHeader hdr;
    hdr.cam_id    = (uint8_t)CAM_DEVICE_ID;
    hdr.frame_no  = frameNo;
    hdr.packet_no = packetNo;
    hdr.checksum  = isLastPacket ? checksum : 0x00;

    // ── UDP 전송 ──────────────────────────────────────────
    udp.beginPacket(udpAddress, udpPort);
    udp.write((const uint8_t*)&hdr, sizeof(hdr));   // 헤더 4B
    udp.write(imageData, chunkSize);                 // JPEG 청크
    udp.endPacket();

    imageData += chunkSize;
    remaining -= chunkSize;
    packetNo++;

    delayMicroseconds(2500);  // 수신 버퍼 과부하 방지
  }
}

// ═══════════════════════════════════════════════════════════
//  loop()
// ═══════════════════════════════════════════════════════════
void loop() {
  static unsigned long lastFrameTime = 0;
  static uint8_t       frameNo       = 0;
  const  unsigned long frameInterval = 100;  // 10 FPS

  unsigned long now = millis();
  if (now - lastFrameTime >= frameInterval) {
    lastFrameTime = now;

    camera_fb_t* fb = esp_camera_fb_get();
    if (fb) {
      sendImageUDP(fb->buf, fb->len, frameNo);
      esp_camera_fb_return(fb);
      frameNo++;   // 0~255 자동 롤오버
    }
  }

  delay(1);   // 시스템 유휴 시간 확보
}