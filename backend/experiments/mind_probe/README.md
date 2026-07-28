# 마음 재해석 과합리(hyper-rationality) 실측 프로브

`reinterpret_mind` 가 실제로 "덜 사람 같은 = 항상 합리적인" 판단만 내놓는지 실 EXAONE
호출로 측정한다. 마음 튜닝(혼란 예시 저작)에 들어갈지 말지를 이 실측이 결정한다 —
과합리가 확인되면 데이터 저작이 정당화되고, 다양하게 나오면 튜닝을 미룬다.

관련 리스크 문헌: LLM 트윈 과합리 (Funhouse Mirrors, arXiv:2509.19088). 아키텍처의
혼란도 주입 숙제(메모리 "남은 숙제 2번")의 선행 실측이다.

## 무엇을 재는가 — 사전 판정 기준 (실행 전에 박아둔다)

조건 6개 × 반복 n회(기본 10) = 60콜, 콜당 약 2초.

| # | 지표 | 과합리 신호 (튜닝 필요) | 사람다움 신호 |
|---|---|---|---|
| 1 | goal 고착도 | 전 조건에서 goal=최상위 끌림점(옛집) ≥ 90% | 조건 따라 시장/null 로 분산 |
| 2 | 혼란도 반응성 | confusion_level 분포가 조건 무관 동일 | 게이지 상태에 따라 이동 |
| 3 | 장면 반응성 | scene(물가/시장) 유무에 출력 무변화 | 장면이 goal·reasoning 에 반영 |
| 4 | 표집 다양성 | 동일 조건 10회 중 고유 (goal,confusion) ≤ 2 | 3개 이상 (분포 표집 전제 성립) |
| 5 | time-shift 발현 | 페르소나에 단서를 줬는데 발현 0% | status/reasoning 에 과거 착각 서사 |
| 6 | status 다양성 | 고유 문구 / 총 호출 < 0.2 | 상황별 문구 변주 |

판정은 개별 지표가 아니라 조합으로: 1·2·3 이 모두 과합리 쪽이면 **튜닝 필요**,
4가 결정적(사실상 결정론)이면 **_MindPool 분포표집 전제 자체가 흔들리는 것**이라
별도 보고. (4는 temperature 0.3 운영값 그대로 잰다.)

## 조건 설계

전부 데모 페르소나 김순자(옛집 0.55 / 정릉시장 0.30, "time-shift" 행동단서 포함).
prior 는 seed 가중치를 그대로 쓴 고정 PriorParams — 재현성 우선.
게이지 보고는 `gauges.report()` 실제 포맷 문자열.

| ID | 경과 | 게이지 | scene | current confusion |
|---|---|---|---|---|
| S1_baseline | 30분 | 전부 중간, 귀소 발동 | 없음 | 0.5 |
| S2_homing | 90분 해질녘 | 귀소 높음 | 없음 | 0.5 |
| S3_anxiety | 60분 | 불안 높음 | 없음 | 0.5 |
| S4_water | 60분 | 불안 높음 | 물가 25m | 0.5 |
| S5_market | 90분 | 귀소 높음 | 시장 40m | 0.5 |
| S6_late_confused | 180분 | 피로·혼란 높음 | 없음 | 0.8 |

S4/S5 는 마음-장면 경로(build_scene_text 포맷)의 반응성을 본다. S5 는 후보에 있는
시장이 눈앞에 보이는 상황 — 목표 전환 유인이 가장 강한 조건.

## 실행

```bash
cd backend
.venv/bin/python experiments/mind_probe/run_probe.py --dry-run   # 배관 점검 (LLM 0회)
.venv/bin/python experiments/mind_probe/run_probe.py             # 실측 (60콜, 약 3분)
.venv/bin/python experiments/mind_probe/run_probe.py --n 5       # 빠른 파일럿 (30콜)
```

선행 조건: EXAONE vLLM 터널 (`ssh -L 8000:localhost:8000 tta@123.37.4.55`).
로컬 8000 을 백엔드가 점유 중이면 다른 포트로 열고 `EXAONE_BASE_URL` 을 맞춘다.
프리플라이트가 엔드포인트 사망을 감지하면 즉시 중단한다 (폴백 응답을 데이터로 오인하지
않기 위해 — reinterpret_mind 의 조용한 폴백("혼란 심화")은 call_log 미증가로 판별).

RAG: 운영 기본값 그대로 (인덱스 있으면 켜짐). 시작 시 활성 여부를 출력에 기록한다 —
`rag_index.npz` 가 로컬에 없으면 꺼진 채 측정되는 것이므로 결과 해석 시 병기할 것.

## 산출물

- `results/probe_raw_<ts>.jsonl` — 콜별 원본 (조건, 프롬프트, 원 JSON, 소요 ms)
- `results/probe_summary_<ts>.md` — 조건별 집계표 + 사전 기준 대조 판정
