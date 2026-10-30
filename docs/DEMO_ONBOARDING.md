# 부스 시연 — 온보딩 템플릿 복제와 턴 리셋 (결선)

체험자가 12문항을 직접 답하지 않는다. **요약 확인 직전 상태의 인터뷰 세션을 템플릿으로
저장해 두고, 체험자마다 새 세션으로 복제**한다. 체험자는 "맞아요"만 답하고, 그 뒤는
기존 확인 게이트가 그대로 돌아 끌림점 좌표화·페르소나 저장이 실제로 일어난다.

한 체험이 끝나면 **진행자가** 보호자 폰 "내 정보" 탭에서 **다음 체험 준비**를 누른다.
그 한 번이 이전 체험(수색 중 사건 → 신고 철회 종결, 페르소나·인터뷰 파기)을 정리하고
새 세션을 복제해 "맞아요" 직전 화면으로 연다. 다음 체험자는 영상부터 보면 된다.

## 앱은 하나, 문은 계정으로 잠근다

앱 번들(doraogil.pages.dev)은 모든 사용자에게 같다. 서버(worker)가 `DEMO_GUARDIAN_IDS`
에 적힌 **부스 보호자 계정 UUID** 에만 `/phase0/demo/*` 를 열고, 그 외 계정은 403 이다.
"내 정보" 탭은 템플릿 조회가 성공한 계정에만 진행자 영역을 보여주므로 일반 사용자 화면은
그대로다. 소유자 id 는 서버가 로그인 계정(auth.uid)으로 강제한다 — 부스 폰은 자기 계정만
리셋할 수 있다.

## 무엇이 추가됐나 (기존 엔진·스키마 무수정)

| 파일 | 역할 |
|---|---|
| `backend/app/api/demo_onboarding.py` | `/phase0/demo/onboarding/*` 라우터 (템플릿 저장·조회, 다음 체험 준비=리셋+복제, 리셋) |
| `backend/app/main.py` | `DEMO_ONBOARDING=true` 일 때만 위 라우터를 얹는다 |
| `backend/app/cloud_bridge/policy.py` | 공개 큐 허용 목록 — 부스 계정만, 소유자 강제 |
| `backend/app/demo_main.py` | 로컬 시연 진입점(환경변수를 켜고 main 을 띄움) |
| `backend/scripts/demo_onboarding_template.py` | (예비) 로컬에서 12문항을 대신 답해 템플릿 파일을 만드는 스크립트 |
| `deploy/supabase/compose.yml` | `CBH_DEMO_ONBOARDING` · `CBH_DEMO_GUARDIAN_IDS` · 템플릿 경로 |
| `frontend/src/api/guardian.ts` | `getDemoTemplate` · `captureDemoTemplate` · `prepareNextDemoTurn` |
| `frontend/src/hooks/queries.ts` | `useDemoBooth` (부스 계정 판별) |
| `frontend/src/navigation/GuardianTabs.tsx` | "내 정보" 탭 진행자 영역(버튼 2개) |
| `frontend/src/screens/RegChatScreen.tsx` | `sessionId` 파라미터로 복제 세션을 그대로 연다 |

경로가 `/phase0/` 아래인 이유: 공개 앱의 Supabase 큐 `cbh_submit` 이 `^/(phase[0-3]|walk|geo)/`
만 통과시킨다. SQL 함수를 다시 적용하지 않기 위해 `/phase0/demo/...` 로 둔다.

## 엔드포인트 (공개 큐 기준 — 소유자는 서버가 넣는다)

| 메서드·경로 | 입력 | 동작 |
|---|---|---|
| `GET /phase0/demo/onboarding/template` | — | 템플릿 요약(이름·나이·대화 줄 수). 없으면 `exists: false`. 부스 계정이 아니면 403 |
| `POST /phase0/demo/onboarding/template` | `{label?, session_id?}` | 이 계정의 **가장 최근 확인 대기 세션**을 템플릿으로 저장(덮어씀). 확인 대기 세션이 없으면 409 |
| `POST /phase0/demo/onboarding/sessions` | `{guardian_name?}` | **다음 체험 준비** — 리셋 후 복제. `{session, reset}` 반환. 템플릿이 없으면 404 이고 아무것도 지우지 않는다 |
| `POST /phase0/demo/onboarding/reset` | — | 리셋만(복제 없음) |

리셋은 정식 파기 경로(`privacy.lifecycle`)를 쓴다: 수색 중 케이스는 `withdrawn` 으로 종결 →
페르소나 파기(연결 케이스·완료 인터뷰 동반) → 미완료 인터뷰 삭제. 감사 로그에
`demo_reset:<guardian_id>` 로 남는다. 복제 세션은 `last_active_at` 을 복제 시각으로 새로 찍는다
(템플릿 시각을 물려받으면 48h TTL 에 바로 걸린다).

템플릿 파일: 배포는 `/app/data/demo/onboarding_template.json`(데이터 볼륨), 로컬 기본
`backend/data/demo/onboarding_template.json`, 환경변수 `DEMO_ONBOARDING_TEMPLATE`.

## 배포 (worker → 앱 순서)

1. GPU 서버 compose 환경에 추가하고 이미지 재빌드·재기동
   ```
   CBH_DEMO_ONBOARDING=true
   CBH_DEMO_GUARDIAN_IDS=<부스 보호자 계정 UUID>[,<UUID>…]
   ```
   UUID 는 Supabase Authentication → Users 의 User UID, 또는 대시보드 피드 `/debug/overview` 의
   `guardian_id`. 이메일은 서버에 없다.
2. 프론트를 `npm run build:web:cloud` 로 빌드해 Pages 에 업로드(플래그 없음 — 계정으로 가른다).
   Supabase env 누락은 이 빌드가 막는다.
3. 대시보드 피드는 v4 이상(`/health` 의 `feed_version`): 인터뷰의 `last_role` 로 "복제됐지만 아직
   답 없음" 세션을 대기 화면으로 판정한다.

## 부스 설치날 순서 (노트북·scp 불필요)

1. 부스 보호자 계정으로 폰에서 "안심 사전 등록"을 평소처럼 진행해 **"이렇게 등록할게요. 맞나요?"**
   요약까지 간다. 집·끌림 장소는 킨텍스 주변으로 답한다(지도 핀이 부스 근처에 잡히게).
   **장소는 지도에서 바로 찾히는 이름**(일산호수공원·대화역처럼 고유명)으로 답한다 — '백석동'처럼 동 이름만 있으면
   "맞아요" 뒤 좌표 확인에 실패해 등록이 보류되고 되묻는다(로컬 실측 10-29).
   **아직 "맞아요"를 보내지 않고 확인 대기 상태에서 템플릿을 저장한다.** 등록을 완료한 세션은 저장 대상이 아니다.
2. "내 정보" 탭 → **지금 대화를 템플릿으로 저장**. 요약 줄에 이름·나이·대화 줄 수가 뜨면 끝.
3. **다음 체험 준비** → 등록 채팅이 요약 상태로 열린다. 대시보드는 대기 화면.
   설치 점검 때 이 복제 세션에 "맞아요"를 보내 등록과 좌표 확인이 완료되는지 확인한 뒤, 다시 **다음 체험 준비**로 대기 상태를 만든다.
4. 체험: 영상(Space) → 체험자 "맞아요" → 등록 완료(대시보드 01 재생) → 신고 → … → 제보.
5. 체험 종료: 보호자 폰 **가족을 찾았어요** → "내 정보" → **다음 체험 준비**(폰이 바로 3번 상태로). 시민 폰은 '상황 종료'
   화면 아래 **처음으로**로 안심 홈에 돌아간다(서버 호출 없음).

   > 10-30 검토: '처음으로'가 서버를 리셋하고 보호자 폰이 폴링으로 요약 화면을 스스로 여는 방식도 만들어 봤으나(앱 커밋
   > b588864), 보이지 않는 연결(서버 대기 파일·5초 폴링·시민 계정 UUID 설정)이 늘어 부스 당일 고장 지점이 많아져 되돌렸다.
   > 누른 폰에서 바로 결과가 보이는 쪽이 운영·설명이 쉽다.

템플릿을 바꾸고 싶으면 1~2 를 다시 하면 된다(worker·앱 재배포 없음). 예비로
`scripts/demo_onboarding_template.py` 로 로컬에서 만들어 데이터 볼륨 `demo/` 에 scp 해도 된다.

## 주의

- "맞아요" 판정은 Mi:dm 호출 1번이 남는다. 정정("집은 ○○동이에요")도 기존 정정 경로 그대로다.
  정정 대화 동안 대시보드는 대기 화면에 머물고 등록이 끝나야 01 로 간다.
- 템플릿은 `InterviewSession` 을 통째로 담는다. 세션 스키마가 바뀌면 복제 시 500 이 나므로
  그때 템플릿을 다시 저장한다(폰에서 2번 다시). 템플릿 검증은 기존 자료 파기 전에 수행한다.
- 리셋은 파기다. `DEMO_GUARDIAN_IDS` 에는 부스 전용 계정만 넣는다.
- 테스트: `tests/test_demo_onboarding.py`(8) · `tests/test_cloud_bridge.py` 의 부스 경로 2개.
- 로컬 실측(10-29): `app.demo_main` + 웹앱(직접 연결) + 로컬 피드로 "내 정보 → 다음 체험 준비 → 요약 화면 → 맞아요 →
  등록 완료(대시보드 대기 → 01) → 다음 체험 준비(가족 삭제·요약 화면·대시보드 대기)" 확인. 직접 연결에서는 앱이
  guardian_id 를 보내야 하므로(큐 정책이 없음) 프론트가 로그인 계정 id 를 함께 보낸다.
