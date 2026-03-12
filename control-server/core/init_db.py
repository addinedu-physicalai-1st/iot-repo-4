"""
DB 마스터 데이터 초기화
- 서버 기동 시 FK(외래키) 제약 조건 충돌을 방지하기 위해 필수 마스터 데이터를 삽입합니다.
- 원본: integrated_server.py → init_base_data()
"""
from database.db_config import get_db_connection


def init_base_data():
    """서버 기동 시 sfam_db의 필수 마스터 데이터를 삽입하여 FK 제약 조건 충돌을 방지합니다."""
    conn = get_db_connection()
    try:
        with conn.cursor() as c:
            # 1. 공통 코드 마스터
            c.execute(
                "INSERT IGNORE INTO node_types (type_id, type_code, type_name) "
                "VALUES (1, 'NURSERY', '육묘장'), (2, 'ROBOT', '로봇구역')"
            )
            c.execute(
                "INSERT IGNORE INTO sensor_types (sensor_type_id, type_name, measure_target, unit) "
                "VALUES (1, 'TEMP', '온도', 'C'), (2, 'HUMI', '습도', '%'), (3, 'LIGHT', '조도', 'Lux'), (4, 'WATER', '수위', '%%')"
            )
            c.execute(
                "INSERT IGNORE INTO actuator_types (actuator_type_id, type_name) "
                "VALUES (1, 'VAL'), (2, 'FAN'), (3, 'LED')"
            )
            c.execute(
                "INSERT IGNORE INTO trigger_sources (trigger_id, trigger_code, trigger_name) "
                "VALUES (1, 'AUTO', '자동 로직')"
            )
            c.execute(
                "INSERT IGNORE INTO agv_status_codes (status_id, status_code, status_name) "
                "VALUES (1, 'IDLE', '대기중'), (2, 'MOVING', '이동중')"
            )

            # 2. 사용자 및 권한 마스터
            c.execute(
                "INSERT IGNORE INTO user_roles (role_id, role_code, role_name) "
                "VALUES (1, 'ADMIN', '시스템관리자')"
            )
            c.execute(
                "INSERT IGNORE INTO users (user_id, role_id, login_id, password_hash, user_name) "
                "VALUES (1, 1, 'admin', 'hash', '시스템')"
            )

            # 3. 작물 및 품종 마스터 (환경 기준값을 위해 필수)
            c.execute(
                "INSERT IGNORE INTO crops (crop_id, crop_name) "
                "VALUES (1, '기본작물')"
            )
            c.execute(
                "INSERT IGNORE INTO seedling_varieties "
                "(variety_id, crop_id, variety_name, opt_temp_day, opt_humidity, opt_light_dli) "
                "VALUES (1, 1, '기본품종', 22.0, 58.0, 2000.0)"
            )
        conn.commit()
        print("✅ [DB Init] sfam_db 마스터 데이터 초기화 완료 (FK 방어벽 가동)")
    except Exception as e:
        print(f"⚠️ [DB Init] 초기화 중 에러 발생: {e}")
    finally:
        conn.close()
