# 돌아오길 프런트엔드 (React Native · Expo)

치매 노인 실종자 조기 발견 앱의 시민·보호자 클라이언트.
평소엔 **산책 앱**(그린), 실종 경보가 뜨면 **수색 도구**(앰버/빨강)로 전환되는 모드 스위칭 구조다.

> **진입 방식은 보호자 신고다**(2026-07-29 전환). 경찰 실종경보 API 자동 연동 설계는 폐기했다.
> 보호자가 앱에서 신고하면 승인 대기 없이 1차 경보가 나간다. 앱은 112를 대체하지 않으며,
> 1차 경보는 재난문자가 아니라 앱 사용자 인앱 알림이다.

운영자(경찰 관제) 화면은 이 앱이 아니라 별도 웹 콘솔 [`../dashboard/`](../dashboard/)에 있다.

## 기술 스택

- **Expo SDK 57**, React Native 0.86, React 19, **TypeScript strict**
- **React Navigation v7** (native-stack + bottom-tabs) — 역할 스위칭·모달·딥링크
- **Zustand** (역할·앱모드·보호자 등록·실종자 단일소스) + **TanStack Query v5**
- **react-native-maps** (실 타일맵 위 POA 히트맵) · **react-native-svg** (범례·게이지·Figma 에셋)
- 폰트는 42dot Sans·HS열음물빛을 번들에 임베드한다(`assets/fonts/`)
- 웹 빌드는 PWA — 서비스워커, 웹푸시(VAPID), 홈 화면 추가 지원

## 실행

```bash
cd frontend
npm ci
npm start        # i = iOS 시뮬레이터, a = Android, w = 웹
```

웹 배포본:

```bash
npm run build:web    # expo export --platform web + 부팅 감시기 주입
```

- 지도는 iOS·Android에서 동작한다. 웹은 지도 플레이스홀더를 쓴다.
- iOS 시뮬레이터는 Apple Maps 기본 제공(키 불필요). Android Google 지도 타일은 API 키가 필요하다.

## 백엔드 연결

`src/api/config.ts`가 접속 경로를 정한다.

| 플랫폼 | 기본 API_BASE |
|---|---|
| 웹 | `/api` — **자기가 서빙된 그 출처**로 부른다. `/api`를 백엔드로 넘기는 일은 nginx(`deploy/nginx.conf`)가 한다 |
| 네이티브 | 배포 서버 절대 주소 |

바꾸려면 `frontend/.env`에 쓰고 Expo를 재시작한다(`EXPO_PUBLIC_` 접두어가 붙은 것만 번들에 주입된다).

```dotenv
EXPO_PUBLIC_API_BASE=http://192.168.0.12:8000
```

- **실기기에서 `localhost`는 백엔드에 절대 닿지 않는다.** 호스트의 LAN IP를 넣어야 한다.
- 웹이 상대 경로를 쓰는 이유: 절대 주소 + 비표준 포트 구성은 학교·사내망에서 막히고, 배포 호스트가 바뀌면 앱을 다시 빌드해야 했다(2026-08-12 공개 경로 이전에서 드러남).
- **`EXPO_PUBLIC_USE_MOCK`은 비워 둔다.** `true`로 켜면 서버에 닿지 않고 목 데이터를 보여준다. 시연장 네트워크가 죽었을 때의 퇴로일 뿐이다.

### 실연동 범위

| 기능 | 백엔드 |
|---|---|
| 보호자 등록·빠른등록·보완 인터뷰 | `/phase0/interviews/sessions*` — 적응형 인터뷰를 그대로 호출 |
| 페르소나 조회·수정 | `/phase0/personas*` |
| 실종 신고 | `/phase1/reports` |
| 확률 지도 | `/phase3/cases/{id}/poa` (폴리곤 포함, 변환 불필요) |
| 시민 제보 | `/phase3/cases/{id}/tips` — `need_more` 되묻기 분기와 전후 면적 변화 매핑 |
| 긴급 알림·안내 | `/phase3/alerts`, `/phase3/alerts/resolved`, `/phase3/cases/{id}/guidance` |
| 산책 | `/walk/*` |
| 웹푸시 | `/phase3/devices`, `/phase3/webpush/public-key` |

고신뢰 제보는 응답 하나가 층2 재예측을 통째로 품는다(실측 29.5초, 새 지역이면 2분 초과). 그래서 제보 요청만 별도의 긴 타임아웃을 쓰고, 끊겨도 **접수 여부를 서버에 다시 확인한 뒤** 이어 간다. 그냥 오류를 올리면 같은 목격이 두 건으로 세어져 확률지도가 왜곡된다.

## 구조

```
src/
├── theme/        디자인 토큰(색 위계·타이포·POA 팔레트), useModeTheme
├── types/        도메인 타입(백엔드 phase0~3 스키마 반영)
├── api/          config · client · guardian · walk · auth
├── store/        authStore · appModeStore · guardianStore · guardianCaseStore
│                 missingPersonStore · engagementStore · debugStore · safeStorage
├── hooks/        TanStack Query 훅, 웹푸시 등록, 산책 추적, 알림 라우팅, 위치
├── navigation/   RootNavigator(역할 게이트) · CitizenTabs · GuardianTabs
├── components/   지도·POA·챗봇·카드·셸 29개
├── screens/      21개 화면
├── pwa.ts        서비스워커 등록과 설치 안내
└── data/         목 데이터(시연장 퇴로 전용)
```

- **시민 탭**: 홈 · 산책 · 알림 · 내 정보
- **보호자 탭**: 홈 · 사전등록 · 알림 · 내 정보

## 아키텍처 핵심 결정

- **모드는 전역 상태, 화면이 아니다.** 산책→수색 전환은 `appModeStore.enterSearch()`가 유일한 트리거다.
- **역할 게이팅.** `authStore.role`이 RootNavigator의 마운트 트리를 결정한다. 시민 트리와 보호자 트리를 컴포넌트 수준에서 분리한다.
- **색 = 상태 심각도.** 긴급 실종경보 빨강, 수색 진행 앰버, 평시 산책 그린. 앰버를 긴급에 쓰지 않는다.
- **POA 히트맵 이중부호화.** 색상+명도에 셀·범례 패턴과 수치 라벨을 더한다. 색약·흑백에서도 순서가 보존된다.
- **접근성.** 최소 15sp + Dynamic Type, 정보성 지도·차트에 `accessibilityLabel`, 터치타깃 48dp.
- **실종자 단일 소스.** 전 화면이 `missingPersonStore.profile`만 참조한다.
- **조용한 폴백을 숨기지 않는다.** 예측 응답의 `prior_source`·`roadnet_used`가 폴백이면 지도 위에 경고 배너를 띄운다.

## 미구현

백그라운드 지오펜스(현재는 앱이 켜져 있을 때만 presence를 올린다), 실기기 푸시 수신 검증.
