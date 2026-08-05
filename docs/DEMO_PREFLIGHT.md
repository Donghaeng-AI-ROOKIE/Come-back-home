# 시연 전 점검 (Demo Preflight)

시연 당일 **처음 도는 경로가 곧 콜드 경로**다. 이 문서의 순서대로 미리 데워 두면
첫 예측에서 조용한 성능 저하가 나가지 않는다.

## 왜 필요한가 — 조용한 폴백 세 가지

세 가지 모두 **실패해도 예측은 정상으로 끝난다.** POA 도 지도도 나오기 때문에
화면만 봐서는 구분할 수 없다. 그래서 계약(API 응답)에 상태를 올려 두었다.

| 폴백 | 무엇이 빠지나 | 계약 필드 | 실측 |
|---|---|---|---|
| EXAONE prior | **개인화 전체** — 연령·유형 평균으로 대체 | `prior_source` | 첫 호출 30초 타임아웃 (2026-08-05) |
| 도로망 | 길 따라 걷는 제약 — 연속 공간으로 대체 | `roadnet_used` | 콜드 다운로드 15~110초 |
| 환경레이어 | 게이지의 환경 항(수풀·물가) | (도로망은 유지) | PIL 미설치로 전체 폴백된 이력 |

### 저장소 초기화가 필요할 때

시연 전에 데이터를 비우려면 파일을 지운다(서버 정지 상태에서).

```bash
rm -f backend/data/storage.db
```

파기 기능을 시연할 거면 지우지 말고 `DELETE /privacy/personas/{id}` 를 쓴다 —
그쪽이 감사 증적을 남기는 정식 경로다.

앱은 이 값으로 지도 위에 붉은 배너를 띄운다. **배너가 보이면 그 예측은 인용하면
안 된다.**

## 순서

### 1. GPU 게이트웨이 확인

```bash
curl -s -m 10 -H "Authorization: Bearer $EXAONE_API_KEY" \
  http://100.73.27.46:18000/v1/models | python3 -m json.tool
```

어댑터 6종(`exaone-sar`·`exaone-axis`·`exaone-mind-dem3` 포함)이 보여야 한다.
안 보이면 맥미니의 SSH 터널과 `tailscale serve` 부터 확인한다.

> Tailscale 을 켜면 Claude Code 가 `ECONNRESET` 으로 죽는다(IPv6 광고 문제).
> `sudo networksetup -setv6off Wi-Fi` 로 미리 막아 둔다.

### 2. 도로망 캐시 예열

캐시 키는 **좌표(소수 4자리) + 반경**이고, 반경은 prior·경과시간으로 정해져
3·4·5·6km 중 하나로 양자화된다. **3km 만 받아 두면 경과시간이 긴 예측에서 또
콜드가 난다** — 좌표당 네 반경을 전부 받아야 한다.

```bash
cd backend
python -m scripts.warm_roadnet 37.6061,127.0106 --env
```

시연에서 쓸 LKP 를 모두 넣는다. 확인만 하려면 `--check` 를 붙인다(다운로드 없음).

### 3. 백엔드 기동 + EXAONE 예열

```bash
cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

기동 시 백그라운드 스레드가 EXAONE 을 짧게 호출해 예열한다(`app.main._warm_exaone`).
로그에 `[warmup] EXAONE 예열 완료` 가 뜨면 된다. 실패해도 기동은 막지 않으므로
로그를 실제로 확인한다.

### 4. 예측 한 번 미리 돌리기

```bash
curl -s -X POST localhost:8000/phase2/cases/case-jeongneung-001/predict > /dev/null
curl -s "localhost:8000/phase3/cases/case-jeongneung-001/poa?top=3" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); \
    print('prior :', d['prior_source'], d['prior_fallback_reason']); \
    print('도로망:', d['roadnet_used'], d['roadnet_fallback_reason'])"
```

기대값:

```
prior : exaone
도로망: True
```

`prior` 가 `fallback`/`stub` 이거나 `도로망` 이 `False` 면 **시연 전에 고친다.**
이 상태로 시연하면 앱에 붉은 배너가 뜬다.

### 5. 앱 연결 확인

`frontend/.env` 의 `EXPO_PUBLIC_API_BASE` 가 백엔드를 가리키는지 본다.

- iOS 시뮬레이터 — `http://localhost:8000` (기본값)
- 실기기 — 호스트의 LAN IP. `localhost` 로는 **절대 안 닿는다**

`EXPO_PUBLIC_USE_MOCK` 은 반드시 비워 둔다. `true` 면 서버에 닿지 않고 목 데이터를
보여준다(이 경우에도 배너가 뜬다 — 목업은 `prior_source=stub` 으로 표시된다).

## 알아 둘 것

- **페르소나는 이제 재시작을 견딘다**(`PERSIST_STORAGE=true`, `data/storage.db`).
  사전등록을 미리 해 두고 당일에 신고만 하는 시나리오가 가능하다.
  다만 `data/` 는 `.gitignore` 대상이고 **개인정보가 들어 있으므로 절대 커밋하지
  않는다.** 시연이 끝나면 `DELETE /privacy/personas/{id}` 로 파기한다.
- **Mi:dm 은 FriendliAI Dedicated 다.** 가동 중이면 과금된다. 시연이 끝나면 내린다.
- 콜드 다운로드가 필요한 좌표를 즉석에서 찍으면 **최대 110초 멈춘다.** 즉흥 시연을
  받을 거면 그 지역을 미리 2번 단계에서 예열해 둔다.
