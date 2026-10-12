# Cloudflare Pages + Supabase + 기존 GPU 서버

휴대폰 → Cloudflare Pages(앱 화면) → Supabase Auth(로그인) →
Supabase 작업 대기열 → GPU 서버의 worker → 기존 FastAPI·AI·보행 엔진 → 작업 결과.

GPU는 외부로 HTTPS 연결만 한다. 맥미니, 노트북, SSH 터널이 실행 경로에 없고
GPU의 80/443 포트를 공개할 필요도 없다. 회원 비밀번호는 Supabase Auth에만 전송하며
작업 테이블이나 GPU에 저장하지 않는다. 기존 SQLite 계정은 자동 이관하지 않는다.

## 현재 상태

2026-10-12 최종 worker `20261012-62b5d88`와 최신 Pages 앱을 배포했다. AI gate는true이며 전체 축 채점OFF, 개인화30/문헌70·res9·5.8㎢를 실제 인증된 예측·조회로 확인했다. 아래 설치·10월8일 기록은 초기 배포 시점 자료다. 현재 결과·범위·롤백은 [최종 서비스 배포 기록](../../docs/releases/final-service-deploy-20261012.md)을 기준으로 한다.

산책 추천 후속 배포는 worker`20261012-walk-45b6086`·웹`315d7811`이다. 예측 정책은 유지했고 [마포구 지도·실제 인증/큐 조회](../../docs/verification/nearby-walks-20261012/README.md)를 확인했다.

## 초기 설치 범위와 제한

- `EXPO_PUBLIC_TRANSPORT=supabase`로 새 전송 경로 선택. 기존 서버 방식은 유지.
- 새 프로젝트 `donghaeng` (`qoprqgnlohnbzbynhchg`). 다른 프로젝트 데이터에 접근하지 않는다.
- 사용자 UUID는 SQL의 auth.uid()에서 결정. 다른 사용자의 인터뷰·가족·사건·산책 조회 차단.
- role 메타데이터는 화면 전환용. 관리자 권한으로 사용하지 않는다.
- 앱에 필요한 경로만 worker가 허용. debug·관리자·기존 비밀번호 API는 차단.
- 시민은 알림·현재 지도·수색 안내·제보를 사용. 타인의 사건 전문과 제보 목록은 조회 불가.
- 시간 미리보기·예측·알림 발송은 사건 소유자만 사용.
- 새 도메인 푸시는 아직 미연결. 공개키 조회는 disabled를 반환하며 기기 구독을 수집하지 않는다.
- 웹 지도 타일은 브라우저에서 OpenStreetMap으로 직접 요청. 실제 휴대폰 망에서 타일 로딩 확인 필요.
- 새 원장·DB·캐시 전용 GPU 디렉터리 사용. 기존 배포·GPU 추론 서버를 중단하지 않는다.
- 기존 AI 설정이 미확인인 상태에서는 `CBH_API_ENABLED=false`. API 503을 명시하고 가짜 예측을 표시하지 않는다.

## 재실행·개인정보

요청 UUID와 생성 시각을 브라우저에 보존하고 재접속 시 같은 결과를 조회한다. 보호자
원문은 저장하지 않는다. 서버가 요청을 받기 전에 연결이 끊긴 경우에는, 소유자 조회로
해당 ID가 없음을 확인한 뒤 같은 UUID를 한 번 재전송한다. 서버의 7일 중복 방지 기간보다
짧은 생성 후 2시간 이내 요청에만 적용한다. 오래된 기록·시각 없는 구버전 기록은 자동
재전송하지 않는다. SQL에서 UUID 중복을 막는다. 실행 중 lease가 만료되면 interrupted로
종료하며 자동으로 다시 실행하지 않는다.
결과 저장 응답이 끊겼을 때만 이미 계산한 결과를 최대 3회 게시한다. API·AI를 다시 호출하지 않는다.

중단된 요청은 자동 재시도할 수 없다. 운영자가 실제 사건·작업 상태를 확인한 뒤 복구해야 한다.
완료 응답 본문은 최대 20분, 미완료 요청 본문은 최대 1시간 보관 후 비운다. UUID와 소유자 등
중복 방지 메타데이터는 7일 후 제거한다. `002_retention.sql`의 분 단위 DB 작업이 필수다.
이는 DB 논리 삭제이며 Supabase의 백업·물리 삭제 보증을 뜻하지 않는다. 실제 개인정보를 받기
전 고지·파기 정책과 공급자 보존 설정을 별도로 확인해야 한다. 현재 배포 검증에는 가상 정보만 사용한다.

## 설치 순서

1. 로컬 검증: backend/tests/test_cloud_bridge.py, frontend/tests/cloud-transport.test.cjs,
   test_sql.sql(PostgreSQL 17), tsc, Expo export.
2. 프로젝트 소유자가 Supabase SQL Editor에서 001_bridge.sql, 002_retention.sql 적용.
   test_sql.sql은 로컬 모의 auth/role을 만드는 테스트 파일이므로 Supabase에 적용하지 않는다.
3. service_role 서버 키를 GPU의 해당 프로젝트 전용 env 파일(0600)에만 보관.
   frontend에는 프로젝트 URL과 publishable 키만 사용. DB 비밀번호는 worker에 필요 없다.
4. GPU compose는 새 cloud data 폴더와 기존 assets 읽기 전용 마운트 사용. 단일 프로세스,
   공개 포트 없음. `CBH_API_ENABLED=false`로 먼저 연결 확인.
5. 기존 K·Mi:dm·RAG·마음모델 설정과 사용량 기록을 확인하고 합성 계정으로 기능 검증.
6. Cloudflare Pages에 frontend/dist 정적 파일 배포. 이메일 인증·실제 휴대폰 확인 필수.
   repo Git 연결은 선택이며 GitHub 접근 권한을 확대하지 않는 direct upload도 가능.

무료 요금제를 선택해도 기존 GPU·모델 API 사용료가 사라지는 것은 아니다.
무료 용량, 이메일 전송 제한, 장기 미접속 프로젝트 정지는 실제 운영 중 확인해야 한다.
현재 수정은 배포 연결 작업이며 마음모델 성능·실제 발견 정확도 개선 실험이 아니다.

## 2026-10-08 추가 확인

- 공개 화면: https://doraogil.pages.dev/ . AI gate는 아직 `false`.
- 실제 Supabase에서 합성 계정 2개의 비밀번호 로그인, 인증된 작업 제출, 다른 계정 결과
  차단, 같은 UUID 중복 제출, 요청 변경 거부, worker 왕복을 확인했다. 총 14개 HTTP 요청,
  모델 호출 0개. `smoke_auth.py`로 재현하며 테스트가 만든 계정만 끝에 삭제한다.
- worker 왕복은 의도한 503 연결 준비 응답까지의 확인이다. AI 정상 응답으로 세지 않는다.
- GPU 안에서 검증된 KINTEX 도로망 78,502노드·226,318간선과 기존 Upstage RAG
  1,200×4,096 배열을 읽었다. 현재 `node_env`는 비어 있다. 도로망 로딩 성공을 환경
  상호작용 검증으로 표현하지 않으며, 환경 입력이 필요한 행동은 따로 확인해야 한다.
- AI 키 이전은 사용자가 승인했지만, 원본 맥미니가 Tailscale 오프라인이어서 이전 0건.
  연결이 복구되면 설정만 한 번 읽고 GPU에 보관한다. 맥미니 서비스 변경은 하지 않는다.
- Supabase custom SMTP는 꺼져 있다. 기본 SMTP는 일반 관람객 가입에 쓸 수 없다.
  [공식 제한](https://supabase.com/docs/guides/auth/auth-smtp)에 따라 별도 SMTP 또는
  사용자와 합의한 부스 임시 계정 흐름이 필요하다. 이메일 인증을 임의로 끄지 않는다.
