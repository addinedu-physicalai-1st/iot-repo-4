# 🌱 통합 스마트팜 자동화 시스템

> IoT 프로젝트 4조 저장소 – 스마트팜

## 프로젝트 개요

육묘(모종 재배) 환경을 자동으로 제어하고, 무인 이송 로봇으로 작물을 운반하며, 관리자 대시보드를 통해 전체 시스템을 실시간으로 관제하는 **통합 스마트팜 자동화 시스템**입니다.

## 프로젝트 구조

```
iot-repo-4/
├── control-server/          # Python 기반 중앙 제어 서버 (DB 연동, 통신)
│   ├── database/
│   │   ├── __init__.py
│   │   └── db_manager.py    # DatabaseManager 클래스 (pymysql)
│   ├── __init__.py
│   ├── main_server.py       # 서버 진입점 (Entry Point)
│   └── requirements.txt
│
├── main-gui/                # Python + PyQt 관리자 관제 대시보드
│   └── README.md
│
├── robot-firmware/          # 무인 이송 시스템 ESP32 펌웨어 (C++)
│   └── README.md
│
├── farm-firmware/           # 육묘 시스템 환경 제어 ESP32 펌웨어 (C++)
│   └── README.md
│
└── README.md
```

## 기술 스택

| 모듈 | 언어 / 프레임워크 | 역할 |
|------|-------------------|------|
| control-server | Python, pymysql | 중앙 제어 서버, AWS EC2 MySQL DB 연동 |
| main-gui | Python, PyQt | 관리자 관제 대시보드 |
| robot-firmware | C++ (ESP32, ESP32 CAM) | 무인 이송 시스템 펌웨어 |
| farm-firmware | C++ (ESP32) | 육묘 환경 제어 펌웨어 |

## 빠른 시작 (control-server)

```bash
cd control-server
pip install -r requirements.txt
python main_server.py
```

## 데이터베이스

- **AWS EC2** 위에 MySQL(MariaDB) 세팅 완료
- DB명: `smart_farm_v2`
- 접속 정보는 `control-server/database/db_manager.py` 에 포함

