# 돌아오길 프런트엔드 (React Native · Expo)

실종자(치매 노인) 조기 발견 앱의 모바일 프런트엔드.
평소엔 **산책 앱**(그린), 경찰 실종경보가 연동되면 **수색 도구**(앰버/빨강)로 전환되는 모드 스위칭 구조.
`돌아오길-RN-스펙.md`의 디자인·IA·시각규칙·아키텍처를 그대로 구현한 스켈레톤(목 데이터로 end-to-end 동작).

> 앱은 실종신고 접수 채널이 아니다. 실제 신고 = 경찰/112. 앱 역할은 (1) 평소 예방 등록(디지털 트윈),
> (2) 경찰 실종경보 자동 연동 기반 AI 동선예측 + 예측동선 내 시민 타겟 경보. **보호자는 앱에서 수동 발동하지 않는다.**

## 기술 스택
- **Expo SDK 57**, React Native 0.86, React 19, **TypeScript strict**
- **React Navigation v7** (native-stack + bottom-tabs) — 역할 스위칭·모달·딥링크
- **Zustand** (전역 모드/역할/실종자 단일소스) + **TanStack Query v5** (서버·경보 동기화)
- **react-native-maps** (실 타일맵 위 POA 히트맵) · **react-native-svg** (범례·게이지·패턴)
- day.js (경과시간)

## 실행
```bash
cd frontend
npm install
npx expo start        # i = iOS 시뮬레이터, a = Android
```
- 지도는 **iOS/Android**에서 동작(웹은 react-native-maps 미지원 → 플레이스홀더).
- iOS 시뮬레이터는 Apple Maps 기본 제공(키 불필요). Android에서 Google 지도 타일은 API 키 필요.
- 데이터는 전부 목(`src/data/mock.ts`). 백엔드 연동은 `src/api/client.ts`의 `USE_MOCK`로 전환.

## 구조
```
src/
├── theme/        디자인 토큰(색 위계·타이포·POA 팔레트), useModeTheme, operatorTheme
├── types/        도메인 타입(백엔드 phase0~3 스키마 반영)
├── data/         MISSING 단일소스, 결정론적 목 데이터(POA 그리드·POI·교차검증 등)
├── api/          타입드 API 클라이언트(목 ↔ 실제 FastAPI 전환)
├── store/        zustand — authStore / appModeStore / missingPersonStore
├── hooks/        TanStack Query 훅 + 파생 골든타임 카운트다운
├── navigation/   RootNavigator(역할 게이트) · CitizenTabs · OperatorStack · 파라미터 타입
├── components/   재사용 라이브러리(지도/시각화·챗봇·카드/셸) 18개
└── screens/      11개 화면 + AuthScreen(역할 선택)
```

## 아키텍처 핵심 결정 (스펙 반영)
- **모드는 전역 상태, 화면이 아님.** 산책→수색 전환은 `appModeStore.enterSearch()`(경찰경보 연동 이벤트)만이 트리거. 수동 hold-to-activate 폐기.
- **3역할 게이팅.** `authStore.role` 클레임이 RootNavigator 마운트 트리를 결정. 운영자(다크 지휘 콘솔)는 시민 트리에서 라우트로 도달 불가 — 트리 자체 분리.
- **색 = 상태 심각도.** 긴급 실종경보=빨강 `#D62839`, 수색 진행=앰버 `#E8703F`, 평시 산책=그린 `#1DA35C`. 앰버를 긴급에 쓰지 않는다.
- **POA 히트맵 이중부호화.** 색상+명도(L\* 30→90) + 셀/범례 패턴(채움·해치·도트·테두리) + 수치 라벨. 색약·흑백에서도 순서 보존.
- **접근성.** 최소 15sp + Dynamic Type(`allowFontScaling`), 저대비 `#8B909A` 폐기, 정보성 지도/차트에 `accessibilityLabel`, 터치타깃 48dp, Pressable.
- **실종자 단일 소스.** 전 화면이 `missingPersonStore.profile`(78세 여성 김순자, 정릉동)만 참조 — "남성/84세" 하드코딩 금지.

## 백엔드 연동

> ⚠️ **계약이 어긋난 상태입니다 (2026-07-22 기준).** 프런트는 2026-07-09 이후 변경이 없는데 백엔드 Phase 3 제보 계약이 바뀌었습니다. 실모드 연동 전에 아래 두 가지를 반드시 반영해야 합니다.
>
> - **`POST /tips` 가 두 형태를 반환합니다.** 정상 접수는 `Tip`, 정보가 부족하면 `{ "status": "need_more", "missing": ["location"|"time"], "reason": str }` 입니다. `status` 키 유무로 분기해야 하며, 되묻기를 받으면 부족한 항목만 물어 **합친 전체 텍스트로 재제출**하거나 `force: true` 로 확정합니다.
> - **제보는 자유 텍스트 한 덩어리입니다.** 현재 프런트의 고정 4단계 챗봇과 달리, 백엔드는 `text` 하나를 받아 위치 지오코딩·시각 변환·구체성 판정을 한 번에 수행합니다. `location`·`seen_at` 은 지도 핀 같은 명시값이 있을 때만 씁니다.
>
> 상세는 루트 [`API_CONTRACT.md`](../API_CONTRACT.md) 를 따르십시오.

`src/api/client.ts`의 `USE_MOCK=false`, `API_BASE`를 실제 서버로 지정. 현재 함수 시그니처와 백엔드 라우트 대응:

| 프런트 호출 | 백엔드 라우트 |
|---|---|
| `getPoaPrediction` | `GET /phase3/cases/{caseId}/poa` (+ `POST /phase2/.../predict` 선행) |
| `submitTip` | `POST /phase3/cases/{caseId}/tips` |
| `sendAlerts` | `POST /phase3/cases/{caseId}/alerts` |
| `getFoundSummary` | `GET /phase1/cases/{caseId}` + 집계 |

(H3 셀 id → 폴리곤 지오메트리 변환기, 교차검증/검증 리포트 매핑은 백엔드 연동 시 채움.)

## 데모 플로우
- **시민**: Auth(시민) → Home → 벨 → LockScreenAlert → AlertDetail → 봤어요 → ReportChat → 전송 → ReportDone → Search
- **보호자**: Home 하단 "데모: 경찰경보 연동" → AlertSync(자동 전환, 발동 UI 없음) → 수색 현황 → Search(수색탭 앰버)
- **운영자**: Auth(운영자) → CommandDashboard(예측/근거/교차검증 + 시간축 0/1/3/6h) → 발견 처리 → CaseFound → 검증 수치

## 미구현 (실서비스 시)
Pretendard 폰트 임베드, 실제 지도 키/스타일, 푸시(Notifee/FCM)·백그라운드 지오펜스 경보 연동, 온보딩·권한·설정.
