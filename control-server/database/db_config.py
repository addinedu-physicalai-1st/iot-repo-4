"""
DB 연결 설정 모듈
- pymysql 기반 raw SQL 연결
"""
import pymysql

db_config_settings = {
    "host": "3.35.24.94",
    "user": "root",
    "password": "Sung!10292748",
    "database": "sfam_db_backup",
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
    "connect_timeout": 5
}


def get_db_connection():
    """pymysql 연결 객체를 반환합니다."""
    return pymysql.connect(**db_config_settings)

