# HomeStudio 법률 문서 (초안)

- `TERMS_OF_SERVICE.md` — 이용약관
- `PRIVACY_POLICY.md` — 개인정보 처리방침
- 서비스 화면: `/terms`, `/privacy` (FastAPI가 이 Markdown을 그대로 HTML로 렌더링, 가입 화면에서 링크 예정)

## 출처와 라이선스

- 생성 도구: [kimlawtech/korean-privacy-terms](https://github.com/kimlawtech/korean-privacy-terms) v4.1 (commit d8934d7), **Apache License 2.0**, Copyright 2026 kimlawtech (SpeciAI) and contributors.
- 사용 방식: 이 도구는 실행형 생성기가 아니라 에이전트 스킬(인터뷰 → Handlebars식 템플릿 치환, `scripts/render.md`)이며, 출력 대상은 Next.js/MDX입니다. 우리는 Next.js를 쓰지 않으므로 템플릿만 사용해 Markdown으로 치환했습니다.
  - 처리방침: `jurisdictions/kr-pipa/privacy-policy.ko.mdx.tmpl` 치환. 조건부 섹션 제외: 민감정보·고유식별정보, 위탁, 제3자 제공 표, 맞춤형 광고, 14세 미만, 자동화된 결정, 국내대리인, 전송요구권. 서비스 특성에 맞게 저장 위치(제5조 보강), 쿠키(세션 쿠키만), 안전성 조치, 영상정보 촬영 안내(제11조 추가)를 수정했습니다.
  - 약관: 한국어 템플릿 `terms-of-service.ko.mdx.tmpl`이 원 저장소에서 빈 파일이라, 같은 폴더의 영문 템플릿 구조와 `references/ftc-standard-terms.md`를 바탕으로 한국어로 작성했습니다. 전자상거래(구매·결제·환불·청약철회) 조항은 해당 없음으로 제외했습니다.
- 원 저장소 고지: 생성 문서는 **참고용 초안이며 법률 자문이 아닙니다**. 외부 사용자에게 제공하기 전 법률 검토 권장. (Apache-2.0 §4에 따라 수정 사실을 각 파일 상단 주석에 표시)

## 미기입 자리표시

| 자리표시 | 문서 |
|---|---|
| `[시행일]`, `[최종 개정일]` | 둘 다 / 처리방침 |
| `[연락처 전화]` | 처리방침 |
| `[보호책임자]`, `[보호책임자 직책]` | 처리방침 |
| `[메타데이터 보유 기간]`, `[접속 기록 보유 기간]` | 처리방침 |
| `[카메라 설치 위치]`, `[촬영 범위]` | 처리방침 |
| `[제공 예정]` (계정 관리 화면·가구 초대) | 둘 다 |
| `[14세 미만 이용 허용 여부 확정 필요]` | 약관 |

연락처 이메일: admin@onestudio.kr (2026-10-10 기입).
