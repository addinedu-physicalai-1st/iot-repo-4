/*
 * ESP32-CAM WiFi 웹캠
 * - JPEG 캡처 후 UDP로 서버(포트 7070)에 전송
 * - 서버의 웹 UI에서 실시간 확인 가능
 *
 * Wi-Fi / 서버 설정은 아래 #define에서 수동 수정
 */

// Wi-Fi / 서버 설정 (수동 수정)
#define WIFI_SSID "addinedu_201class_4-2.4G"
#define WIFI_PASSWORD "201class4!"
#define SERVER_IP "192.168.0.132"
#define SERVER_TCP_PORT 8080
#define SERVER_UDP_PORT 7070

#include "esp_camera.h"
#include <WiFi.h>
#include <WiFiUdp.h>

// 장비별 고유 ID (다중 카메라 시 1, 2, 3... 변경)
#define DEVICE_ID 1

WiFiUDP udp;

// 2. AI-Thinker 카메라 핀 맵핑 (다른 보드는 camera_pins.h 참고)
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

void setup() {
  Serial.begin(115200);
  Serial.println("\n--- ESP32-CAM 10FPS UDP 스트리밍 ---");

  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 10000000;
  config.pixel_format = PIXFORMAT_JPEG;

  config.frame_size = FRAMESIZE_QVGA;
  config.jpeg_quality = 10;
  config.fb_count = 3;
  config.grab_mode = CAMERA_GRAB_LATEST;

  esp_err_t err = esp_camera_init(&config);

  if (err != ESP_OK) {
    Serial.printf("카메라 초기화 실패: 0x%x", err);
    delay(1000);
    ESP.restart();
  }

  Serial.println("[WiFi] 연결 시도 중...");
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  WiFi.setSleep(false);

  int timeout = 20;  // 10초 (500ms × 20)
  while (WiFi.status() != WL_CONNECTED && timeout > 0) {
    delay(500);
    Serial.print(".");
    timeout--;
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("[WiFi] 연결됨. IP: %s, RSSI: %ddBm\n",
                  WiFi.localIP().toString().c_str(), WiFi.RSSI());
    Serial.println("UDP 스트리밍 시작!");
    Serial.printf("전송 대상: %s:%d\n", SERVER_IP, SERVER_UDP_PORT);
    Serial.flush();
  } else {
    Serial.println("[WiFi] 연결 실패! 5초 후 재시작...");
    delay(5000);
    ESP.restart();
  }
}

void sendImageUDP(uint8_t *imageData, size_t imageSize, uint8_t frameNo, uint8_t vehicleId) {
  size_t remainingSize = imageSize;
  uint8_t packetNo = 0;

  uint8_t checksum = 0;
  for (size_t i = 0; i < imageSize; i++) {
    checksum += imageData[i];
  }

  while (remainingSize > 0) {
    size_t chunkSize = std::min(remainingSize, (size_t)1024);
    bool isLastPacket = (remainingSize <= 1024);

    udp.beginPacket(SERVER_IP, SERVER_UDP_PORT);
    udp.write(vehicleId);
    udp.write(frameNo);
    udp.write(packetNo);
    udp.write(isLastPacket ? checksum : (uint8_t)0);
    udp.write(imageData, chunkSize);
    udp.endPacket();

    imageData += chunkSize;
    remainingSize -= chunkSize;
    packetNo++;
    delayMicroseconds(2500);
  }
}

void loop() {
  static bool wasConnected = true;

  if (WiFi.status() != WL_CONNECTED) {
    if (wasConnected) {
      Serial.println("[WiFi] 연결 끊김 - 재연결 시도 중...");
      wasConnected = false;
    }
    static unsigned long lastAttempt = 0;
    if (millis() - lastAttempt > 5000) {
      lastAttempt = millis();
      WiFi.reconnect();
    }
    delay(100);
    return;
  }

  if (!wasConnected) {
    Serial.printf("[WiFi] 재연결됨. IP: %s\n", WiFi.localIP().toString().c_str());
    wasConnected = true;
  }

  static unsigned long lastFrameTime = 0;
  static uint8_t frameNo = 0;
  const unsigned long frameInterval = 100;  // 10 FPS

  unsigned long now = millis();
  if (now - lastFrameTime >= frameInterval) {
    lastFrameTime = now;

    camera_fb_t *fb = esp_camera_fb_get();
    if (fb) {
      sendImageUDP(fb->buf, fb->len, frameNo, DEVICE_ID);
      esp_camera_fb_return(fb);
      frameNo++;
    }
  }
  delay(1);
}
