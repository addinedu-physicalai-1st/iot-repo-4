"""
search_device_manager.py
========================
입출고 키트(Search Device) 관리 모듈.
SA 다이어그램의 '입출고키트' 컴포넌트에 대응한다.

역할:
    - 입고장 RFID 리더기로 모종 품종 식별 (SR-06, SR-12, SR-14)
    - 품종 → 육묘 섹션 매핑 (SR-10, SR-15)
    - 빈 저장고 탐색 후 운송 작업 생성 (SR-16, SR-17)
    - 출고장 안착 검증 (SR-37)

의존성:
    - FarmRepository       : 품종 조회, 빈 슬롯 검색
    - TransportTaskQueue   : 운송 작업 큐에 Task 등록
"""

from database.farm_repository import FarmRepository
from domain.transport_task import TransportTaskQueue


class SearchDeviceManager:
    """
    입출고 키트를 관리하고, RFID 인식 → 품종 매핑 → 운송 작업 등록의
    전체 입고 워크플로우를 조율하는 매니저 클래스.
    """

    def __init__(self, farm_repo: FarmRepository, task_queue: TransportTaskQueue):
        """
        Args:
            farm_repo  : FarmRepository 인스턴스 (DI)
            task_queue : TransportTaskQueue 인스턴스 (DI)
        """
        self.farm_repo = farm_repo
        self.task_queue = task_queue

    # ──────────── RFID 리딩 처리 (SR-14) ────────────
    def handle_rfid_read(self, rfid_value: str, station_node_id: str):
        """
        입고장의 RFID 리더기에서 모종을 인식했을 때 호출된다.

        처리 흐름 (SR-12 ~ SR-17):
            1) RFID 값으로 DB에서 품종 정보 조회 (SR-10, SR-14)
            2) 품종에 맞는 육묘 섹션 배정 (SR-15)
            3) 해당 섹션에서 빈 저장고 탐색 (SR-16)
            4) 빈 저장고가 있으면 운송 작업 생성 (SR-17)
            5) 빈 저장고가 없으면 사용자 앱에 알림

        Args:
            rfid_value      : RFID 카드에서 읽은 값
            station_node_id : RFID 리더기가 설치된 입고장 노드 ID
        """
        print(f"📡 [SearchDevice] RFID 리딩: {rfid_value} (입고장: {station_node_id})")

        # 1) RFID → 품종 매핑 조회
        #    TODO (팀원 구현): RFID 값과 variety_id를 매핑하는 테이블/로직
        #    현재는 rfid_value를 그대로 variety_id로 변환 시도
        variety_id = self._lookup_variety_by_rfid(rfid_value)
        if variety_id is None:
            print(f"❌ [SearchDevice] RFID 매핑 실패: {rfid_value} → 알 수 없는 품종")
            # TODO: SR-20 – 사용자 앱에 경고 알림 전송
            return

        # 2) 품종 정보 조회
        variety = self.farm_repo.get_variety_by_id(variety_id)
        if variety:
            print(f"🌱 [SearchDevice] 품종 확인: {variety.get('crop_name')} "
                  f"- {variety.get('variety_name')}")

        # 3) 품종에 맞는 빈 저장고 탐색 (SR-15, SR-16)
        available_slots = self.farm_repo.find_section_for_variety(variety_id)

        if not available_slots:
            print(f"⚠️ [SearchDevice] 품종 {variety_id}에 맞는 빈 저장고 없음!")
            # TODO: 사용자 앱에 '빈 공간 없음' 알림 전송
            return

        # 4) 첫 번째 빈 슬롯을 목적지로 하여 입고 운송 작업 생성 (SR-17)
        destination = available_slots[0]
        dest_node_id = destination["node_id"]

        task = self.task_queue.create_inbound_task(
            source_node=station_node_id,
            destination_node=dest_node_id,
            variety_id=variety_id,
        )
        print(f"✅ [SearchDevice] 입고 작업 생성 완료: "
              f"{station_node_id} → {dest_node_id} (Task #{task.task_id})")

    # ──────────── 출고 안착 검증 (SR-37) ────────────
    def verify_outbound_delivery(self, station_node_id: str) -> bool:
        """
        출고장에 모종이 정상적으로 하차되었는지 검증한다.

        Args:
            station_node_id : 출고장 노드 ID

        Returns:
            검증 성공 여부

        TODO (팀원 구현):
            - 출고장 카메라 또는 센서로 실제 안착 여부 확인
            - 확인 완료 시 DB에서 해당 저장고 상태 초기화 (SR-38)
        """
        print(f"🔍 [SearchDevice] 출고 안착 검증 중... (출고장: {station_node_id})")
        # TODO: 카메라/센서 기반 검증 로직 구현
        pass
        return True

    # ──────────── RFID → 품종 매핑 (내부 메서드) ────────────
    def _lookup_variety_by_rfid(self, rfid_value: str) -> int | None:
        """
        RFID 값에서 품종 ID를 매핑한다.

        TODO (팀원 구현):
            - DB에 RFID ↔ variety_id 매핑 테이블 조회
            - 또는 RFID 카드 자체에 variety_id가 인코딩되어 있다면 파싱
        """
        # 임시 구현: rfid_value가 숫자 문자열이면 variety_id로 변환
        try:
            return int(rfid_value)
        except ValueError:
            return None
