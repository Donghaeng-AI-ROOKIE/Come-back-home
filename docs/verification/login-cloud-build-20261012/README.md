# 웹 로그인 빌드 설정 누락 수정 — 2026-10-12

## 재현과 원인

실제 `doraogil.pages.dev/Auth`에서 합성 잘못된 계정으로 로그인하면 “연결에 실패했습니다. 네트워크를 확인해 주세요.”가 표시됐다. 사용자에게도 같은 오류가 발생했다. 개인 비밀번호나 입력 값을 읽지 않았다.

교체 전 production은 `68abffec-ac6d-49ef-a021-c563ff355a0f`, entry는 `index-31f8eef03eee1d6a8348c68e5bd6d738.js`였다. 실제 내려받은 compiled Supabase 모듈의 `CLOUD_TRANSPORT=false`이며 Supabase URL·공개키도 주입되지 않았다. 그래서 기존 `/api/auth/login` 경로로 요청했다. 정적 Pages에는 해당 기존 API가 없다. API에 직접 인증한 이전 worker 검증과 브라우저 인증 성공은 별개이며, 이전 초기 화면·JS 로딩 확인만으로 로그인까지 확인했다고 해석할 수 없다. [실제 구 번들 검사](before.json).

## 수정

`npm run build:web:cloud -- --env-file /path/to/protected-public.env`를 Pages 업로드의 정본 명령으로 추가했다.

- Supabase transport, URL, publishable/anon 키, mock OFF 필수 검사. 서버 secret/service_role 키 거부.
- 로컬 dotenv의 덮어쓰기 방지, Metro `--clear` 재빌드.
- 출력된 Expo entry의 auth 설정 모듈을 격리 stub으로 실행해 실제 transport·URL·공개키 일치 확인. 빌드 환경만 보고 성공 처리하지 않는다.
- `cloud-build.json`에 프로젝트 호스트·entry 해시·빌드 시각·소스 기준 커밋 기록. 키는 기록하지 않는다.

새 빌드의 Supabase 계약 검사, 재발 경계 테스트5개, 기존 cloud transport 테스트7개와 TypeScript 검사 통과. 예측 엔진·worker 이미지·30:70·res9·5.8㎢ 정책은 변경하지 않는다.

## 인증 정책과 별도 한계

Supabase 이메일 확인·비밀번호·권한 정책은 유지한다. 기존 SQLite 계정은 자동 이전하지 않는다. 실제 사용자가 입력한 계정/비밀번호로 로그인하지 않았으며, 합성 검사 결과를 해당 사용자의 비밀번호나 이메일 확인 상태 검증으로 확대하지 않는다. 기본 SMTP의 일반 관람객 가입 제한도 별도 문제다.

이 파일에 배포 ID·실제 공개 번들 검증·브라우저 합성 정상 로그인·재접속 결과를 추가한다. 새 모델 호출과 실제 푸시를 수행하지 않는다. 사용량은 공용 원장에 남기며 비용은null/미확인이다.
