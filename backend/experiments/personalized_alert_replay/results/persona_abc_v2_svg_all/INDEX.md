# 전량 렌더링 인덱스

시나리오 27개 x 시점 4개 = 108장.
각 SVG는 A/B/C 3패널이다. 검정 점선 = D1(실종지점 k-ring 2, 세 군 공통), 검정 실선 = 그 군이 예측으로 고른 알림 셀(D1 제외분), 빨간 선 = 정답 이동 경로, 파란 원 = 실종 지점, 빨간 마름모 = 정답 목적지, 색면 = POA 확률.

| 시나리오 | 층 | 행동 | 0분 | 45분 | 90분 | 135분 |
|---|---|---|---|---|---|---|
| SP02-consistent | consistent | 왕복·순환형 | ABC | ABC | ABC | ABC |
| SP02-counter | counter | 왕복·순환형 | ABC | ABC | ABC | ABC |
| SP02-neutral | neutral | 왕복·순환형 | ABC | ABC | ABC | ABC |
| SP03-consistent | consistent | 지속 이동형 | ABC | ABC | ABC | ··C |
| SP03-counter | counter | 지속 이동형 | ABC | ABC | ABC | ABC |
| SP03-neutral | neutral | 지속 이동형 | ABC | ABC | ABC | ABC |
| SP04-consistent | consistent | 지속 이동형 | ABC | ABC | ·BC | ··· |
| SP04-counter | counter | 지속 이동형 | ABC | ABC | ABC | ABC |
| SP04-neutral | neutral | 지속 이동형 | ABC | ABC | A·· | ··· |
| SP05-consistent | consistent | 정지 후 재이동·은폐형 | ABC | ABC | ABC | ··C |
| SP05-counter | counter | 정지 후 재이동·은폐형 | ABC | ··· | ··· | ··· |
| SP05-neutral | neutral | 정지 후 재이동·은폐형 | ABC | ··· | ··· | ··· |
| SP06-consistent | consistent | 정지형 | ABC | ABC | ABC | ABC |
| SP06-counter | counter | 정지형 | ABC | ABC | ABC | ABC |
| SP06-neutral | neutral | 정지형 | ABC | ABC | ABC | ABC |
| SP07-consistent | consistent | 지속 이동형 | ABC | ABC | ABC | ABC |
| SP07-counter | counter | 지속 이동형 | ABC | ABC | ABC | AB· |
| SP07-neutral | neutral | 지속 이동형 | ABC | ABC | ABC | ABC |
| SP08-consistent | consistent | 왕복·순환형 | ABC | ABC | ABC | ABC |
| SP08-counter | counter | 왕복·순환형 | ABC | ABC | ABC | ABC |
| SP08-neutral | neutral | 왕복·순환형 | ABC | ABC | ABC | ABC |
| SP09-consistent | consistent | 지속 이동형 | ABC | ABC | ABC | A·C |
| SP09-counter | counter | 지속 이동형 | ABC | ABC | ·B· | ABC |
| SP09-neutral | neutral | 지속 이동형 | ABC | ABC | ABC | ABC |
| SP10-consistent | consistent | 정지 후 재이동·은폐형 | ABC | ABC | ABC | ··· |
| SP10-counter | counter | 정지 후 재이동·은폐형 | ABC | ABC | ABC | ··· |
| SP10-neutral | neutral | 정지 후 재이동·은폐형 | ABC | ·B· | ·BC | ··· |

표기: 적중한 군의 알파벳만 표시하고 실패는 `·`. 예) `A·C` = A 성공, B 실패, C 성공.

적중은 '정답 위치가 그 군의 알림 셀(D1 + 예측 19셀) 안에 있었는가'이며, 실제 푸시 전달·열람·제보·발견을 뜻하지 않는다.
