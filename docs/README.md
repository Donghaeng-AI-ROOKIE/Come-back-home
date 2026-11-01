# 문서 안내

처음 읽는 분은 [프로젝트 README](../README.md)에서 최종 구성과 대표 결과를 확인한 뒤 아래 문서로 이동합니다. **최종 정책은 개인화 30% + 독립 문헌통계 70%, res9, 최대 5.8㎢이며 전체 축 채점은 OFF**입니다.

## 최종 구현과 실행

| 목적 | 문서 |
|---|---|
| 등록·신고·수색 지도·제보·발견 안내 원본 12장 | [서비스 화면과 출처](SERVICE_SCREENS_20261101.md) |
| 현재 실행 아키텍처, 처리 흐름, 폴백과 코드 근거 | [11월 1일 아키텍처](ARCHITECTURE_20261101.md) |
| 부스 계정의 템플릿 복제·턴 리셋 | [부스 시연 안내](DEMO_ONBOARDING.md) |
| 운영 앱 화면, 같은 사건의 iPhone 푸시와 지도 | [실제 서비스 화면](SERVICE_SCREENS_20261026.md) |
| 모델 역할, SAR 초기 prior, 마음 규칙, 전체 흐름 | [서비스 E2E 구조](SERVICE_E2E_20261012.md) |
| 전송 경계, 신고, 제보, 지도 조회 계약 | [API 계약](../API_CONTRACT.md) |
| Cloudflare Pages, Supabase, CPU worker와 GPU 모델 연결 | [배포 연결 안내](../deploy/supabase/README.md) |
| 최종 정책과 후보 선택 근거 | [정책 확정](experiments/final-alert-policy-20261012.md) |
| 발표용 상세 비교와 질문 답변 | [발표 참고 자료](PRESENTATION_FINAL_20261012.md) |

## 성능 근거 — 같은 표끼리 비교

| 실험 | 역할 | 구분 |
|---|---|---|
| [본선 대비 최종 성능, 방향 후보](experiments/directional-alert-safety-20261012/README.md) | README의 63.00%, 효율 +28.18% 근거 | 경로 seed 1251–1253. 방향 추가와 res8 후보는 미채택 |
| [개인화 제거 대조](experiments/personal-first-alert-balanced-20261012/README.md) | 문헌통계 단독 대비 개인화 효과 확인 | 경로 seed 1231–1233. 위 표와 다른 경로 |
| [개인별 SAR70 대조](experiments/final-sar-literature-comparison-20261012/README.md) | 70%도 개인별 SAR 파라미터를 사용하는 후보와 최종안 비교 | 경로 seed 1261–1263. 최종 독립 문헌통계 유지 |
| [시간 오류 영향 및 수치 재확인](verification/final-evidence-audit-20261023/README.md) | 저장 자료와 원시 판정 감사 | 10월 23일 로컬 확인. 새로운 보행 실험 아님 |

각 실험은 기존 합성 인물의 경로를 바꿔 비교했습니다. 경로 seed가 다른 표의 수치를 하나의 동일 조건 비교로 합치지 않습니다. 반복 시점을 사람 수로 세지 않습니다.

## 날짜별 서비스 검증

- [10월 28–29일 화면 캡처와 11월 1일 문서 정리](SERVICE_SCREENS_20261101.md)
- [10월 26일 운영 화면과 실제 iPhone 알림](SERVICE_SCREENS_20261026.md)
- [10월 26일 사용량 원장 메모리 복구](verification/usage-ledger-memory-20261026/README.md)

- [최종 정책 최초 배포](releases/final-service-deploy-20261012.md)
- [인증, 등록, 모델, 예측, 제보, 종결 점검](verification/service-full-audit-20261012/README.md)
- [로그인 빌드 수정](verification/login-cloud-build-20261012/README.md)
- [산책 추천 복구](verification/nearby-walks-20261012/README.md)
- [신고와 화면 흐름](verification/app-flow-20261010/README.md)

위 자료는 해당 실행 시점의 증빙입니다. 이후 #294–#296의 종결 사건 조회 및 제보 응답 개선까지 #297을 통해 main에 반영됐습니다. 운영 이미지나 라이브 상태를 확인한 날짜와 Git 병합 날짜를 구분합니다.

## 과거 구현과 실험

아래 자료는 개발 과정과 재현 근거로 보존합니다. 최신 설정 및 성능의 기준은 위의 최종 문서입니다.

- [과거 구현 아키텍처](IMPLEMENTATION_ARCHITECTURE.md), [과거 시연 점검](DEMO_PREFLIGHT.md)
- [초기 개인화 알림 실험](../backend/experiments/personalized_alert_replay/results/V2_RESULTS.md)
- [독립 채널 복구](experiments/independent-channels-alerts-20261011/README.md)
- [문헌 거리 안전망](experiments/sar-distance-safety-20261012/README.md)
- [미채택 개인화10% 후보](experiments/nonpersonal-alert-balanced-20261012/README.md)
- [추가 면적 후보](experiments/area-alert-fresh-routes-20261012/README.md)

`assets/screens/`와 8월 구조 이미지는 과거 UI 및 설계 자료입니다. 현재 배포 화면의 증빙으로 재사용하지 않습니다. 실험 그림의 ‘현재’는 작성 당시 비교 기준이며, 미채택 후보 색상을 최종 발송 구역으로 설명하지 않습니다.
