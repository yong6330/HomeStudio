# Backend

HomeStudio의 이벤트 정규화, 메타데이터 저장, 활동 집계, 로컬 API를 담당한다.

## Planned Responsibilities

- `DATA_EVENT_SPEC.md` 기반 이벤트 검증
- SQLite 메타데이터와 미디어 참조
- 시간대별·일별 활동 집계
- 상태/활동/이벤트/미디어 API
- 보존 정책과 저장 공간 보호
- 카메라·CSI 구현과 분리된 사용자 계약

## Not Started

기술 스택과 실행 방식은 P1 환경 검증 후 확정한다. 제품 코드는 P0 승인 전 생성하지 않는다.

관련 문서:

- `docs/01_product/PRD_HAMSTER_MVP.md`
- `docs/02_technology/DATA_EVENT_SPEC.md`
- `docs/02_technology/DEVELOPMENT_GUIDELINES.md`
