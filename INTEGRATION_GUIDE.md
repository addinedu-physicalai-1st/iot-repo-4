# 📋 시스템 통합 가이드 (2026-03-10)

> **작성 목적**: `iot-repo-4_v2.1`에 있던 중앙서버/육묘시스템 코드를 레포 구조에 맞게 통합한 내역 정리

---

## 🔀 무엇이 바뀌었나?

### 요약

| 영역 | 변경 전 | 변경 후 |
|------|---------|---------|
| 중앙서버 | `integrated_server.py` 1개 파일 (582줄) | `control-server/` 아래 **모듈 분리** (4개 패키지, 12개 파일) |
| 모니터링 앱 | `monitor_app.py` 별도 파일 | `main-gui/monitor_app.py`에 배치 |
| 육묘 펌웨어 | `smart_farm_nursery/` 별도 폴더 | `farm-firmware/` 아래 3개 스케치 |
| DB 비밀번호 | 코드에 하드코딩 | `.env` 파일에서 읽기 (`.env.example` 참고) |

---

## 📂 새로 추가된 파일 목록

### `control-server/` — 중앙 제어 서버

```
control-server/
├── main_server.py          ← 🚀 서버 실행 진입점
├── requirements.txt         ← pip 의존성
├── templates/
│   └── index.html           ← 웹 대시보드
├── database/                ← DB 연결 및 모델
│   ├── __init__.py
│   ├── db_config.py         ← pymysql 연결 (.env에서 읽기)
│   ├── database.py          ← SQLAlchemy 엔진
│   ├── models.py            ← ORM 모델
│   └── schemas.py           ← Pydantic 스키마
├── core/                    ← 핵심 비즈니스 로직
│   ├── __init__.py
│   ├── node_identifier.py   ← ESP32 ID → 노드/제어기 ID 매핑
│   ├── sensor_controller.py ← 센서 데이터 처리 + 제어 명령 생성
│   └── init_db.py           ← DB 마스터 데이터 초기화
├── network/                 ← 통신
│   ├── __init__.py
│   ├── tcp_robot_server.py  ← 로봇 TCP 서버 (포트 8000)
│   └── task_dispatcher.py   ← 자동 배차 루프 (3초 주기)
└── domain/                  ← API 라우트 (Flask Blueprint)
    ├── __init__.py
    ├── rfid_handler.py      ← RFID 카드 인식 처리
    ├── robot_api.py         ← 로봇 제어/비상정지 API
    └── environment_api.py   ← 환경 설정/레이아웃 API
```

### `main-gui/` — 모니터링 앱
```
main-gui/
└── monitor_app.py    ← PyQt6 실시간 그래프/테이블 모니터링
```

### `farm-firmware/` — 육묘 ESP32 펌웨어 **(새 디렉토리)**
```
farm-firmware/
├── nursery-sensor/
│   └── nursery-sensor.ino       ← 센서 노드 (온도/습도/조도)
├── nursery-bridge/
│   └── nursery-bridge.ino       ← Serial-TCP 브리지 (Arduino ↔ WiFi)
└── nursery-cam/
    └── nursery-cam.ino          ← ESP32-CAM UDP 영상 스트리밍
```

### 기존 파일 변경
```
.env.example  ← DB 설정 변수 추가 (DB_HOST, DB_USER, DB_PASSWORD, DB_NAME 등)
```

---

## 🚀 실행 방법

### 1. 중앙 서버 실행

```bash
# 1) .env 파일 설정 (최초 1회)
cp .env.example .env
# .env 파일 열어서 DB_PASSWORD를 실제 비밀번호로 수정

# 2) 의존성 설치
cd control-server
pip install -r requirements.txt

# 3) 서버 실행
python main_server.py
```

서버 시작 시:
- Flask 웹서버: **포트 5001**
- 로봇 TCP 서버: **포트 8000**
- 자동 배차 루프: 3초 주기

### 2. 모니터링 앱 실행

```bash
cd main-gui
pip install PyQt6 pyqtgraph requests python-dotenv
python monitor_app.py        # 기본: s11 노드
python monitor_app.py s12    # 특정 노드 지정
```

---

## ⚠️ 주의사항

### `.env` 파일 필수 설정
기존에 코드에 직접 박혀있던 DB 비밀번호를 `.env` 파일로 분리했습니다.
**`.env`가 없어도 기본값(하드코딩)으로 동작하므로 당장 문제는 없지만**, 보안을 위해 설정 권장:

```bash
# .env 파일 내용
DB_HOST=3.35.24.94
DB_USER=root
DB_PASSWORD=실제비밀번호
DB_NAME=sfam_db_backup
FLASK_PORT=5001
TCP_PORT=8000
```

### 기존 `server/` 폴더는 그대로
기존 `server/app.py`는 **건드리지 않았습니다**. 포트가 다르므로 (5000 vs 5001) 동시 실행 가능합니다.

### ESP32 펌웨어 WiFi 설정
`farm-firmware/` 내 `.ino` 파일들의 WiFi SSID/비밀번호는 아직 코드에 직접 작성되어 있습니다.
실제 환경에 맞게 수정 후 업로드하세요.

---

## 🔧 원본 → 분리 매핑 참고표

`integrated_server.py`의 함수들이 어디로 갔는지:

| 원본 함수/코드 | 이동된 위치 |
|----------------|------------|
| `identify_node()` | `core/node_identifier.py` |
| `process_sensor_and_control()` | `core/sensor_controller.py` |
| `init_base_data()` | `core/init_db.py` |
| `tcp_robot_server()`, `handle_robot_client()` | `network/tcp_robot_server.py` |
| `task_dispatcher_loop()` | `network/task_dispatcher.py` |
| `/api/rfid`, `/api/rfid_inoutbound` 라우트 | `domain/rfid_handler.py` |
| `/api/robot/control`, `/api/robot/emergency_stop` | `domain/robot_api.py` |
| `/api/set_environment`, `/api/get_layout` 등 | `domain/environment_api.py` |
| DB 연결 설정 (하드코딩) | `database/db_config.py` (.env 연동) |
| `if __name__ == '__main__':` | `main_server.py` |
