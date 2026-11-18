# Vision

IP 카메라 연결, 프레임 처리, 움직임 감지, 클립 생성, 햄스터 검출·추적을 담당한다.

## Phase Boundaries

1. P1: TVS-W1000 스트림 연결성 확인
2. P2: 움직임 이벤트와 클립
3. P4: 햄스터 검출·추적과 활동량 고도화

## Constraints

- Pentium 4415U/4GB에서 상시 운전
- 무제한 프레임 큐 금지
- 감지와 보관 품질 분리
- 모델 실패 시 기본 움직임 기능 유지
- 실제 영상 벤치마크 전 모델 채택 금지

관련 문서:

- `docs/02_technology/SYSTEM_ARCHITECTURE.md`
- `docs/03_research/OSS_MODEL_REGISTER.md`
