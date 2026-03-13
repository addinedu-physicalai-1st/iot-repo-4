-- ============================================================
--  File    : 01_schema.sql
-- ============================================================

CREATE DATABASE IF NOT EXISTS sfam_db_backup
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE sfam_db_backup;

SET FOREIGN_KEY_CHECKS = 0;


-- ============================================================
-- SECTION 1. 공통 코드 테이블 (11개)
-- ============================================================

DROP TABLE IF EXISTS crops;
CREATE TABLE crops (
  crop_id      TINYINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '작물 고유 ID',
  crop_name    VARCHAR(50)      NOT NULL                COMMENT '작물명',
  crop_name_en VARCHAR(50)          NULL                COMMENT '영문 작물명',
  PRIMARY KEY (crop_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='작물 마스터';

DROP TABLE IF EXISTS suppliers;
CREATE TABLE suppliers (
  supplier_id   TINYINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '공급처 고유 ID',
  supplier_name VARCHAR(100)     NOT NULL                COMMENT '공급처명',
  PRIMARY KEY (supplier_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='공급처 마스터';

DROP TABLE IF EXISTS diseases;
CREATE TABLE diseases (
  disease_id      TINYINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '병해 고유 ID',
  disease_name    VARCHAR(100)     NOT NULL                COMMENT '병해명',
  disease_name_en VARCHAR(100)         NULL                COMMENT '영문 병해명',
  PRIMARY KEY (disease_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='병해 마스터';

DROP TABLE IF EXISTS node_types;
CREATE TABLE node_types (
  type_id   TINYINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '타입 고유 ID',
  type_code VARCHAR(20)      NOT NULL                COMMENT '타입 코드',
  type_name VARCHAR(50)      NOT NULL                COMMENT '타입명',
  PRIMARY KEY (type_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='노드 타입 코드';

DROP TABLE IF EXISTS agv_status_codes;
CREATE TABLE agv_status_codes (
  status_id   TINYINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '상태 고유 ID',
  status_code VARCHAR(20)      NOT NULL                COMMENT '상태 코드',
  status_name VARCHAR(50)      NOT NULL                COMMENT '상태명',
  PRIMARY KEY (status_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AGV 상태 코드';

DROP TABLE IF EXISTS error_codes;
CREATE TABLE error_codes (
  error_id   SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '에러 고유 ID',
  error_code VARCHAR(20)       NOT NULL                COMMENT '에러 코드',
  error_name VARCHAR(100)      NOT NULL                COMMENT '에러명',
  severity   TINYINT UNSIGNED  NOT NULL                COMMENT '심각도 1:INFO 2:WARN 3:ERROR',
  PRIMARY KEY (error_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='에러 코드 마스터';

DROP TABLE IF EXISTS sensor_types;
CREATE TABLE sensor_types (
  sensor_type_id TINYINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '센서 타입 고유 ID',
  type_name      VARCHAR(50)      NOT NULL                COMMENT '센서 모델/종류',
  measure_target VARCHAR(50)      NOT NULL                COMMENT '측정 대상',
  unit           VARCHAR(10)      NOT NULL                COMMENT '측정 단위',
  PRIMARY KEY (sensor_type_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='센서 타입 마스터';

DROP TABLE IF EXISTS actuator_types;
CREATE TABLE actuator_types (
  actuator_type_id TINYINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '액추에이터 타입 ID',
  type_name        VARCHAR(50)      NOT NULL                COMMENT '장치 종류',
  type_name_ko     VARCHAR(50)          NULL                COMMENT '장치 한글명',
  PRIMARY KEY (actuator_type_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='액추에이터 타입 마스터';

DROP TABLE IF EXISTS trigger_sources;
CREATE TABLE trigger_sources (
  trigger_id   TINYINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '트리거 고유 ID',
  trigger_code VARCHAR(20)      NOT NULL                COMMENT '트리거 코드',
  trigger_name VARCHAR(50)      NOT NULL                COMMENT '트리거명',
  PRIMARY KEY (trigger_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='트리거 원인 코드';

DROP TABLE IF EXISTS action_types;
CREATE TABLE action_types (
  action_type_id SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '액션 타입 고유 ID',
  action_code    VARCHAR(50)       NOT NULL                COMMENT '액션 코드',
  action_name    VARCHAR(100)      NOT NULL                COMMENT '액션명',
  target_system  VARCHAR(20)       NOT NULL                COMMENT '대상 시스템',
  PRIMARY KEY (action_type_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='액션 타입 코드';

DROP TABLE IF EXISTS permissions;
CREATE TABLE permissions (
  permission_id   TINYINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '권한 항목 고유 ID',
  permission_code VARCHAR(50)      NOT NULL                COMMENT '권한 코드',
  permission_name VARCHAR(100)     NOT NULL                COMMENT '권한명',
  PRIMARY KEY (permission_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='권한 항목 마스터';


-- ============================================================
-- SECTION 2. 사용자 및 권한
-- ============================================================

DROP TABLE IF EXISTS user_roles;
CREATE TABLE user_roles (
  role_id   TINYINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '권한 그룹 고유 ID',
  role_code VARCHAR(20)      NOT NULL                COMMENT '권한 식별 코드',
  role_name VARCHAR(50)      NOT NULL                COMMENT '권한명',
  PRIMARY KEY (role_id),
  UNIQUE KEY uk_role_code (role_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='권한 그룹';

DROP TABLE IF EXISTS role_permissions;
CREATE TABLE role_permissions (
  role_id       TINYINT UNSIGNED NOT NULL COMMENT '권한 그룹 ID',
  permission_id TINYINT UNSIGNED NOT NULL COMMENT '권한 항목 ID',
  PRIMARY KEY (role_id, permission_id),
  CONSTRAINT fk_rp_role       FOREIGN KEY (role_id)       REFERENCES user_roles  (role_id),
  CONSTRAINT fk_rp_permission FOREIGN KEY (permission_id) REFERENCES permissions (permission_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='권한-항목 M:N 연결';

DROP TABLE IF EXISTS users;
CREATE TABLE users (
  user_id       INT UNSIGNED     NOT NULL AUTO_INCREMENT                 COMMENT '사용자 고유 ID',
  role_id       TINYINT UNSIGNED NOT NULL                                COMMENT '권한 그룹 ID',
  login_id      VARCHAR(50)      NOT NULL                                COMMENT '로그인 아이디',
  password_hash VARCHAR(255)     NOT NULL                                COMMENT '암호화된 비밀번호',
  user_name     VARCHAR(50)      NOT NULL                                COMMENT '사용자 실명',
  phone_number  VARCHAR(20)          NULL                                COMMENT '연락처',
  is_active     BOOLEAN          NOT NULL DEFAULT TRUE                   COMMENT '계정 활성화 여부',
  last_login_at TIMESTAMP            NULL                                COMMENT '마지막 접속 시간',
  created_at    TIMESTAMP        NOT NULL DEFAULT CURRENT_TIMESTAMP      COMMENT '계정 생성일',
  PRIMARY KEY (user_id),
  UNIQUE KEY uk_login_id (login_id),
  CONSTRAINT fk_users_role FOREIGN KEY (role_id) REFERENCES user_roles (role_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='사용자 계정';

DROP TABLE IF EXISTS user_action_logs;
CREATE TABLE user_action_logs (
  log_id         BIGINT UNSIGNED   NOT NULL AUTO_INCREMENT           COMMENT '행동 로그 ID',
  user_id        INT UNSIGNED      NOT NULL                          COMMENT '실행한 사용자 ID',
  action_type_id SMALLINT UNSIGNED NOT NULL                          COMMENT '액션 타입 ID',
  target_id      VARCHAR(50)           NULL                          COMMENT '제어 대상 기기 ID',
  action_detail  JSON                  NULL                          COMMENT '상세 내용 JSON',
  action_result  TINYINT UNSIGNED      NULL                          COMMENT '0:FAIL 1:SUCCESS 2:PARTIAL',
  action_time    TIMESTAMP             NULL                          COMMENT '명령 실행 시간',
  PRIMARY KEY (log_id),
  CONSTRAINT fk_ual_user   FOREIGN KEY (user_id)        REFERENCES users        (user_id),
  CONSTRAINT fk_ual_action FOREIGN KEY (action_type_id) REFERENCES action_types (action_type_id),
  INDEX idx_ual_user_time (user_id, action_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='사용자 행동 로그';


-- ============================================================
-- SECTION 3. 품종 및 작물 관리
-- ============================================================

DROP TABLE IF EXISTS seedling_varieties;
CREATE TABLE seedling_varieties (
  variety_id      SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT      COMMENT '품종 고유 ID',
  crop_id         TINYINT UNSIGNED  NOT NULL                     COMMENT '작물 ID',
  supplier_id     TINYINT UNSIGNED      NULL                     COMMENT '공급처 ID',
  variety_name    VARCHAR(100)      NOT NULL                     COMMENT '세부 품종명',
  opt_temp_day    DECIMAL(5,2)          NULL                     COMMENT '주간 목표 온도(℃)',
  opt_temp_night  DECIMAL(5,2)          NULL                     COMMENT '야간 목표 온도(℃)',
  opt_humidity    DECIMAL(5,2)          NULL                     COMMENT '목표 습도(%)',
  opt_ec          DECIMAL(4,2)          NULL                     COMMENT '목표 양액 농도(EC)',
  opt_ph          DECIMAL(4,2)          NULL                     COMMENT '목표 산성도(pH)',
  opt_light_dli   DECIMAL(5,2)          NULL                     COMMENT '일적산광량(DLI)',
  days_to_harvest SMALLINT UNSIGNED     NULL                     COMMENT '정식 후 수확 일수',
  disease_bitmask TINYINT UNSIGNED      NULL DEFAULT 0           COMMENT '내병성 비트마스크',
  characteristics TEXT                  NULL                     COMMENT '기타 메모',
  is_active       BOOLEAN           NOT NULL DEFAULT TRUE        COMMENT '사용 여부',
  PRIMARY KEY (variety_id),
  CONSTRAINT fk_sv_crop     FOREIGN KEY (crop_id)     REFERENCES crops     (crop_id),
  CONSTRAINT fk_sv_supplier FOREIGN KEY (supplier_id) REFERENCES suppliers (supplier_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='품종 마스터';

DROP TABLE IF EXISTS variety_diseases;
CREATE TABLE variety_diseases (
  variety_id       SMALLINT UNSIGNED NOT NULL COMMENT '품종 ID',
  disease_id       TINYINT UNSIGNED  NOT NULL COMMENT '병해 ID',
  resistance_level TINYINT UNSIGNED  NOT NULL COMMENT '내성 수준 1:약 2:보통 3:강',
  PRIMARY KEY (variety_id, disease_id),
  CONSTRAINT fk_vd_variety FOREIGN KEY (variety_id) REFERENCES seedling_varieties (variety_id),
  CONSTRAINT fk_vd_disease FOREIGN KEY (disease_id) REFERENCES diseases           (disease_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='품종-병해 M:N 연결';


-- ============================================================
-- SECTION 4. 농장 구역 및 노드
-- ============================================================

DROP TABLE IF EXISTS farm_nodes;
CREATE TABLE farm_nodes (
  node_id            VARCHAR(50)       NOT NULL                  COMMENT '물리적 노드 ID',
  current_variety_id SMALLINT UNSIGNED     NULL                  COMMENT '식재된 품종 ID',
  node_name          VARCHAR(100)      NOT NULL                  COMMENT '노드 명칭',
  node_type_id       TINYINT UNSIGNED  NOT NULL                  COMMENT '노드 타입 ID',
  controller_mac     VARCHAR(17)           NULL                  COMMENT '환경 제어 보드 MAC',
  current_quantity   SMALLINT UNSIGNED     NULL DEFAULT 0        COMMENT '현재 적재 수량',
  max_capacity       SMALLINT UNSIGNED     NULL                  COMMENT '최대 수용 수량',
  pos_x              SMALLINT UNSIGNED     NULL                  COMMENT 'UI 도면 X 좌표',
  pos_y              SMALLINT UNSIGNED     NULL                  COMMENT 'UI 도면 Y 좌표',
  is_active          BOOLEAN           NOT NULL DEFAULT TRUE     COMMENT '노드 사용 가능 여부',
  PRIMARY KEY (node_id),
  CONSTRAINT fk_fn_variety   FOREIGN KEY (current_variety_id) REFERENCES seedling_varieties (variety_id),
  CONSTRAINT fk_fn_node_type FOREIGN KEY (node_type_id)       REFERENCES node_types         (type_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='구역별 노드';


-- ============================================================
-- SECTION 5. NFC 카드 관리 ★신규
-- ============================================================

DROP TABLE IF EXISTS nfc_cards;
CREATE TABLE nfc_cards (
  nfc_uid      CHAR(8)          NOT NULL                           COMMENT 'NFC UID (4bytes HEX 8자)',
  card_type    TINYINT UNSIGNED NOT NULL                           COMMENT '1=NODE 2=TRAY 3=WORKER',
  card_version TINYINT UNSIGNED NOT NULL DEFAULT 1                 COMMENT '카드 데이터 버전',
  farm_id      SMALLINT UNSIGNED    NULL                           COMMENT '소속 농장 ID',
  ref_id       VARCHAR(50)          NULL                           COMMENT '연결 대상 ID',
  card_label   VARCHAR(16)          NULL                           COMMENT '카드 라벨 문자열',
  issued_date  DATE             NOT NULL                           COMMENT '발급일',
  is_active    BOOLEAN          NOT NULL DEFAULT TRUE              COMMENT '카드 활성 여부',
  created_at   TIMESTAMP        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '등록 시각',
  PRIMARY KEY (nfc_uid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin COMMENT='NFC 카드 마스터 ★신규';

DROP TABLE IF EXISTS trays;
CREATE TABLE trays (
  tray_id       SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT             COMMENT '트레이 고유 ID',
  nfc_uid       CHAR(8)           NOT NULL                            COMMENT 'NFC UID',
  variety_id    SMALLINT UNSIGNED NOT NULL                            COMMENT '품종 ID',
  crop_id       TINYINT UNSIGNED  NOT NULL                            COMMENT '작물 ID',
  supplier_id   TINYINT UNSIGNED      NULL                            COMMENT '공급처 ID',
  tray_capacity TINYINT UNSIGNED  NOT NULL DEFAULT 50                 COMMENT '트레이 총 셀 수',
  current_qty   TINYINT UNSIGNED  NOT NULL DEFAULT 0                  COMMENT '현재 묘 수량',
  growth_stage  TINYINT UNSIGNED      NULL                            COMMENT '1=SEEDING 2=GERMINATION 3=SEEDLING 4=TRANSPLANT 5=GROWING 6=HARVEST',
  tray_status   TINYINT UNSIGNED  NOT NULL DEFAULT 1                  COMMENT '1=NORMAL 2=IN_TRANSIT 3=EMPTY 4=DAMAGED',
  seeding_date  DATE                  NULL                            COMMENT '파종일',
  planting_date DATE                  NULL                            COMMENT '정식일',
  is_active     BOOLEAN           NOT NULL DEFAULT TRUE               COMMENT '트레이 사용 여부',
  created_at    TIMESTAMP         NOT NULL DEFAULT CURRENT_TIMESTAMP  COMMENT '등록 시각',
  PRIMARY KEY (tray_id),
  UNIQUE KEY uk_tray_nfc (nfc_uid),
  CONSTRAINT fk_trays_nfc      FOREIGN KEY (nfc_uid)     REFERENCES nfc_cards          (nfc_uid),
  CONSTRAINT fk_trays_variety  FOREIGN KEY (variety_id)  REFERENCES seedling_varieties (variety_id),
  CONSTRAINT fk_trays_crop     FOREIGN KEY (crop_id)     REFERENCES crops              (crop_id),
  CONSTRAINT fk_trays_supplier FOREIGN KEY (supplier_id) REFERENCES suppliers          (supplier_id),
  CONSTRAINT chk_qty_range     CHECK (current_qty >= 0 AND current_qty <= tray_capacity)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='묘판 트레이 마스터 ★신규';


-- ============================================================
-- SECTION 6. AGV 로봇
-- ============================================================

DROP TABLE IF EXISTS agv_robots;
CREATE TABLE agv_robots (
  agv_id        VARCHAR(20)      NOT NULL        COMMENT '차량 고유 ID',
  mac_address   VARCHAR(17)          NULL        COMMENT '통신 모듈 MAC',
  model_name    VARCHAR(50)          NULL        COMMENT '기체 모델명',
  status_id     TINYINT UNSIGNED     NULL        COMMENT '상태 ID',
  battery_level TINYINT UNSIGNED     NULL        COMMENT '배터리 잔량(%)',
  last_ping     TIMESTAMP            NULL        COMMENT '마지막 통신 시간',
  PRIMARY KEY (agv_id),
  UNIQUE KEY uk_agv_mac (mac_address),
  CONSTRAINT fk_agv_status FOREIGN KEY (status_id) REFERENCES agv_status_codes (status_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AGV 라인트레이서 마스터';

DROP TABLE IF EXISTS transport_tasks;
CREATE TABLE transport_tasks (
  task_id          INT UNSIGNED      NOT NULL AUTO_INCREMENT     COMMENT '작업 고유 ID',
  agv_id           VARCHAR(20)       NOT NULL                    COMMENT '할당된 기체 ID',
  variety_id       SMALLINT UNSIGNED NOT NULL                    COMMENT '운반 품종 ID',
  source_node      VARCHAR(50)       NOT NULL                    COMMENT '출발지 노드 ID',
  destination_node VARCHAR(50)       NOT NULL                    COMMENT '목적지 노드 ID',
  ordered_by       INT UNSIGNED      NOT NULL                    COMMENT '지시자 user_id',
  quantity         SMALLINT UNSIGNED NOT NULL                    COMMENT '운반 수량',
  task_status      TINYINT UNSIGNED  NOT NULL DEFAULT 0          COMMENT '0:PENDING 1:IN_PROGRESS 2:DONE 3:FAIL',
  ordered_at       TIMESTAMP             NULL                    COMMENT '지시 시간',
  started_at       TIMESTAMP             NULL                    COMMENT '작업 시작 시간',
  completed_at     TIMESTAMP             NULL                    COMMENT '작업 완료 시간',
  PRIMARY KEY (task_id),
  CONSTRAINT fk_tt_agv FOREIGN KEY (agv_id)           REFERENCES agv_robots         (agv_id),
  CONSTRAINT fk_tt_var FOREIGN KEY (variety_id)       REFERENCES seedling_varieties (variety_id),
  CONSTRAINT fk_tt_src FOREIGN KEY (source_node)      REFERENCES farm_nodes         (node_id),
  CONSTRAINT fk_tt_dst FOREIGN KEY (destination_node) REFERENCES farm_nodes         (node_id),
  CONSTRAINT fk_tt_usr FOREIGN KEY (ordered_by)       REFERENCES users              (user_id),
  INDEX idx_tt_agv_status (agv_id, task_status),
  INDEX idx_tt_ordered_at (ordered_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='운송 지시';

DROP TABLE IF EXISTS agv_telemetry_logs;
CREATE TABLE agv_telemetry_logs (
  log_id            BIGINT UNSIGNED   NOT NULL AUTO_INCREMENT COMMENT '로그 고유 ID',
  agv_id            VARCHAR(20)       NOT NULL               COMMENT '기체 ID',
  task_id           INT UNSIGNED          NULL               COMMENT '수행 중인 작업 ID',
  current_node      VARCHAR(50)           NULL               COMMENT '현재 통과 노드 ID',
  line_sensor_state TINYINT UNSIGNED      NULL               COMMENT '라인 센서 비트마스크',
  motor_speed_left  TINYINT UNSIGNED      NULL               COMMENT '좌측 모터 PWM',
  motor_speed_right TINYINT UNSIGNED      NULL               COMMENT '우측 모터 PWM',
  error_id          SMALLINT UNSIGNED     NULL               COMMENT '에러 ID',
  logged_at         TIMESTAMP             NULL               COMMENT '로그 발생 시간',
  PRIMARY KEY (log_id),
  CONSTRAINT fk_atl_agv  FOREIGN KEY (agv_id)       REFERENCES agv_robots      (agv_id),
  CONSTRAINT fk_atl_task FOREIGN KEY (task_id)      REFERENCES transport_tasks (task_id),
  CONSTRAINT fk_atl_node FOREIGN KEY (current_node) REFERENCES farm_nodes      (node_id),
  CONSTRAINT fk_atl_err  FOREIGN KEY (error_id)     REFERENCES error_codes     (error_id),
  INDEX idx_atl_agv_time (agv_id, logged_at),
  INDEX idx_atl_task     (task_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AGV 주행 로그';

DROP TABLE IF EXISTS task_status_history;
CREATE TABLE task_status_history (
  history_id  BIGINT UNSIGNED   NOT NULL AUTO_INCREMENT              COMMENT '이력 고유 ID',
  task_id     INT UNSIGNED      NOT NULL                             COMMENT '대상 운송 작업 ID',
  from_status TINYINT UNSIGNED      NULL                             COMMENT '변경 전 상태 (NULL=최초)',
  to_status   TINYINT UNSIGNED  NOT NULL                             COMMENT '변경 후 상태 0~3',
  changed_by  INT UNSIGNED          NULL                             COMMENT '변경 주체 user_id',
  agv_id      VARCHAR(20)           NULL                             COMMENT '수행 AGV ID',
  node_idx    TINYINT UNSIGNED      NULL                             COMMENT '상태 변경 발생 노드 인덱스',
  reason      VARCHAR(100)          NULL                             COMMENT '변경 사유',
  changed_at  TIMESTAMP         NOT NULL DEFAULT CURRENT_TIMESTAMP   COMMENT '변경 시각',
  PRIMARY KEY (history_id),
  CONSTRAINT fk_tsh_task FOREIGN KEY (task_id)    REFERENCES transport_tasks (task_id),
  CONSTRAINT fk_tsh_user FOREIGN KEY (changed_by) REFERENCES users           (user_id),
  CONSTRAINT fk_tsh_agv  FOREIGN KEY (agv_id)     REFERENCES agv_robots      (agv_id),
  INDEX idx_tsh_task_time (task_id, changed_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='운송 작업 상태 이력 ★신규';


-- ============================================================
-- SECTION 7. 육묘장 환경 제어
-- ============================================================

DROP TABLE IF EXISTS nursery_controllers;
CREATE TABLE nursery_controllers (
  controller_id  VARCHAR(50)      NOT NULL                      COMMENT '제어기 ID',
  node_id        VARCHAR(50)      NOT NULL                      COMMENT '설치된 구역 노드 ID',
  mac_address    VARCHAR(17)          NULL                      COMMENT '보드 MAC 주소',
  ip_address     INT UNSIGNED         NULL                      COMMENT 'IPv4 정수 저장 (INET_ATON)',
  control_mode   TINYINT UNSIGNED     NULL DEFAULT 1            COMMENT '0:MANUAL 1:AUTO',
  device_status  TINYINT UNSIGNED     NULL DEFAULT 1            COMMENT '0:OFFLINE 1:ONLINE',
  last_heartbeat TIMESTAMP            NULL                      COMMENT '마지막 통신 수신 시간',
  PRIMARY KEY (controller_id),
  UNIQUE KEY uk_ctrl_mac (mac_address),
  CONSTRAINT fk_nc_node FOREIGN KEY (node_id) REFERENCES farm_nodes (node_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='육묘장 환경 제어기';

DROP TABLE IF EXISTS nursery_sensors;
CREATE TABLE nursery_sensors (
  sensor_id      SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '센서 고유 ID',
  controller_id  VARCHAR(50)       NOT NULL               COMMENT '연결된 컨트롤러 ID',
  sensor_type_id TINYINT UNSIGNED  NOT NULL               COMMENT '센서 타입 ID',
  pin_number     TINYINT UNSIGNED  NOT NULL               COMMENT '연결 핀 번호',
  PRIMARY KEY (sensor_id),
  CONSTRAINT fk_ns_ctrl FOREIGN KEY (controller_id)  REFERENCES nursery_controllers (controller_id),
  CONSTRAINT fk_ns_type FOREIGN KEY (sensor_type_id) REFERENCES sensor_types        (sensor_type_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='센서';

DROP TABLE IF EXISTS nursery_sensor_logs;
CREATE TABLE nursery_sensor_logs (
  log_id      BIGINT UNSIGNED   NOT NULL AUTO_INCREMENT COMMENT '로그 고유 번호',
  sensor_id   SMALLINT UNSIGNED NOT NULL               COMMENT '센서 ID',
  value       DECIMAL(10,2)     NOT NULL               COMMENT '실제 측정값',
  measured_at TIMESTAMP         NOT NULL               COMMENT '데이터 측정 시각',
  PRIMARY KEY (log_id),
  CONSTRAINT fk_nsl_sensor FOREIGN KEY (sensor_id) REFERENCES nursery_sensors (sensor_id),
  INDEX idx_nsl_sensor_time (sensor_id, measured_at),
  INDEX idx_nsl_measured_at (measured_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='센서 수집 로그';

DROP TABLE IF EXISTS nursery_actuators;
CREATE TABLE nursery_actuators (
  actuator_id      SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '액추에이터 고유 ID',
  controller_id    VARCHAR(50)       NOT NULL               COMMENT '제어 컨트롤러 ID',
  actuator_type_id TINYINT UNSIGNED  NOT NULL               COMMENT '액추에이터 타입 ID',
  pin_number       TINYINT UNSIGNED  NOT NULL               COMMENT '제어 신호 핀 번호',
  PRIMARY KEY (actuator_id),
  CONSTRAINT fk_na_ctrl FOREIGN KEY (controller_id)    REFERENCES nursery_controllers (controller_id),
  CONSTRAINT fk_na_type FOREIGN KEY (actuator_type_id) REFERENCES actuator_types      (actuator_type_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='구동기';

DROP TABLE IF EXISTS nursery_actuator_logs;
CREATE TABLE nursery_actuator_logs (
  log_id      BIGINT UNSIGNED   NOT NULL AUTO_INCREMENT COMMENT '로그 고유 번호',
  actuator_id SMALLINT UNSIGNED NOT NULL               COMMENT '동작한 액추에이터 ID',
  state_value VARCHAR(10)       NOT NULL               COMMENT '변경된 상태 ON/OFF/PWM값',
  trigger_id  TINYINT UNSIGNED  NOT NULL               COMMENT '트리거 원인 ID',
  logged_at   TIMESTAMP         NOT NULL               COMMENT '동작 시각',
  PRIMARY KEY (log_id),
  CONSTRAINT fk_nal_actuator FOREIGN KEY (actuator_id) REFERENCES nursery_actuators (actuator_id),
  CONSTRAINT fk_nal_trigger  FOREIGN KEY (trigger_id)  REFERENCES trigger_sources   (trigger_id),
  INDEX idx_nal_actuator_time (actuator_id, logged_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='구동기 제어 로그';


-- ============================================================
-- SECTION 8. 출하 관리 ★신규
-- ============================================================

DROP TABLE IF EXISTS shipment_logs;
CREATE TABLE shipment_logs (
  shipment_id     INT UNSIGNED      NOT NULL AUTO_INCREMENT COMMENT '출하 고유 ID',
  tray_id         SMALLINT UNSIGNED NOT NULL               COMMENT '출하 트레이 ID',
  variety_id      SMALLINT UNSIGNED NOT NULL               COMMENT '출하 품종 ID',
  qty_shipped     TINYINT UNSIGNED  NOT NULL               COMMENT '출하 수량',
  dest_node       VARCHAR(50)           NULL               COMMENT '출하 목적지 노드 ID',
  task_id         INT UNSIGNED          NULL               COMMENT '연관 운송 작업 ID',
  shipped_by      INT UNSIGNED      NOT NULL               COMMENT '출하 처리 user_id',
  shipment_status TINYINT UNSIGNED  NOT NULL DEFAULT 0     COMMENT '0:PENDING 1:IN_PROGRESS 2:DONE 3:CANCELLED',
  shipped_at      TIMESTAMP         NOT NULL               COMMENT '출하 완료 시각',
  PRIMARY KEY (shipment_id),
  CONSTRAINT fk_sl_tray    FOREIGN KEY (tray_id)    REFERENCES trays              (tray_id),
  CONSTRAINT fk_sl_variety FOREIGN KEY (variety_id) REFERENCES seedling_varieties (variety_id),
  CONSTRAINT fk_sl_node    FOREIGN KEY (dest_node)  REFERENCES farm_nodes         (node_id),
  CONSTRAINT fk_sl_task    FOREIGN KEY (task_id)    REFERENCES transport_tasks    (task_id),
  CONSTRAINT fk_sl_user    FOREIGN KEY (shipped_by) REFERENCES users              (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='출하 기록 ★신규';


-- ============================================================
-- SECTION 9. 상태 이력 ★신규
-- ============================================================

DROP TABLE IF EXISTS tray_status_history;
CREATE TABLE tray_status_history (
  history_id  BIGINT UNSIGNED   NOT NULL AUTO_INCREMENT              COMMENT '이력 고유 ID',
  tray_id     SMALLINT UNSIGNED NOT NULL                             COMMENT '대상 트레이 ID',
  from_status TINYINT UNSIGNED      NULL                             COMMENT '변경 전 tray_status (NULL=최초)',
  to_status   TINYINT UNSIGNED  NOT NULL                             COMMENT '변경 후 tray_status 1~4',
  task_id     INT UNSIGNED          NULL                             COMMENT '연관 운송 작업 ID',
  node_idx    TINYINT UNSIGNED      NULL                             COMMENT '변경 발생 노드 인덱스',
  current_qty TINYINT UNSIGNED      NULL                             COMMENT '수량 스냅샷',
  changed_by  INT UNSIGNED          NULL                             COMMENT '변경 주체 user_id (NULL=자동)',
  changed_at  TIMESTAMP         NOT NULL DEFAULT CURRENT_TIMESTAMP   COMMENT '변경 시각',
  PRIMARY KEY (history_id),
  CONSTRAINT fk_tsh2_tray FOREIGN KEY (tray_id)    REFERENCES trays           (tray_id),
  CONSTRAINT fk_tsh2_task FOREIGN KEY (task_id)    REFERENCES transport_tasks (task_id),
  CONSTRAINT fk_tsh2_user FOREIGN KEY (changed_by) REFERENCES users           (user_id),
  INDEX idx_tsh2_tray_time (tray_id, changed_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='트레이 상태 전이 이력 ★신규';


-- ============================================================
-- TRIGGERS (4개)
-- ============================================================

DROP TRIGGER IF EXISTS trg_task_status_history;
DROP TRIGGER IF EXISTS trg_tray_status_history;
DROP TRIGGER IF EXISTS trg_shipment_done;
DROP TRIGGER IF EXISTS trg_tray_damaged;

DELIMITER $$

CREATE TRIGGER trg_task_status_history
AFTER UPDATE ON transport_tasks FOR EACH ROW
BEGIN
  IF OLD.task_status <> NEW.task_status THEN
    INSERT INTO task_status_history (task_id, from_status, to_status, agv_id, changed_at)
    VALUES (NEW.task_id, OLD.task_status, NEW.task_status, NEW.agv_id, NOW());
  END IF;
END$$

CREATE TRIGGER trg_tray_status_history
AFTER UPDATE ON trays FOR EACH ROW
BEGIN
  IF OLD.tray_status <> NEW.tray_status THEN
    INSERT INTO tray_status_history (tray_id, from_status, to_status, current_qty, changed_at)
    VALUES (NEW.tray_id, OLD.tray_status, NEW.tray_status, NEW.current_qty, NOW());
  END IF;
END$$

CREATE TRIGGER trg_shipment_done
AFTER UPDATE ON shipment_logs FOR EACH ROW
BEGIN
  IF OLD.shipment_status <> 2 AND NEW.shipment_status = 2 THEN
    UPDATE trays SET tray_status = 3, current_qty = 0
    WHERE tray_id = NEW.tray_id AND tray_status <> 4;
  ELSEIF OLD.shipment_status <> 3 AND NEW.shipment_status = 3 THEN
    UPDATE trays SET tray_status = 1
    WHERE tray_id = NEW.tray_id AND tray_status = 2;
  END IF;
END$$

CREATE TRIGGER trg_tray_damaged
AFTER UPDATE ON trays FOR EACH ROW
BEGIN
  IF OLD.tray_status <> 4 AND NEW.tray_status = 4 THEN
    UPDATE trays SET is_active = FALSE WHERE tray_id = NEW.tray_id;
  ELSEIF OLD.tray_status = 4 AND NEW.tray_status <> 4 THEN
    UPDATE trays SET is_active = TRUE  WHERE tray_id = NEW.tray_id;
  END IF;
END$$

DELIMITER ;

SET FOREIGN_KEY_CHECKS = 1;

-- ============================================================
-- END OF 01_schema.sql  (31 Tables · 10 Indexes · 4 Triggers)
-- ============================================================
