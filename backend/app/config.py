"""전역 설정. .env 로 오버라이드 가능 (.env.example 참고)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # 모델 API 키 — 비어 있으면 해당 클라이언트는 스텁 모드
    exaone_api_key: str = ""
    midm_api_key: str = ""
    varco_api_key: str = ""
    upstage_api_key: str = ""
    tip_llm_api_key: str = ""

    # KT 믿음(Mi:dm) 서빙 엔드포인트 (OpenAI 호환 chat completions)
    #   midm_base_url   = 발급받은 endpoint URL (…/v1 또는 …/v1/chat/completions 앞부분)
    #   midm_model      = 발급받은 endpoint ID (chat 요청의 model 필드로 들어감)
    midm_base_url: str = ""
    midm_model: str = ""
    llm_timeout: float = 30.0        # LLM HTTP 타임아웃(초)

    # LG EXAONE 서빙 엔드포인트 (OpenAI 호환 chat completions) — Mi:dm 과 같은 규약
    #   exaone_base_url = 발급받은 endpoint URL (…/v1 또는 …/v1/chat/completions 앞부분)
    #   exaone_model    = 발급받은 endpoint ID (chat 요청의 model 필드로 들어감)
    exaone_base_url: str = ""
    exaone_model: str = ""

    # Phase 3 제보 구조화 전용 — 모델 미정(2026-07-21, Mi:dm 에서 분리).
    # OpenAI 호환 chat completions 전제로 셋 다 채우면 실동작, 비어 있으면 스텁.
    #   tip_llm_base_url = 발급받은 endpoint URL
    #   tip_llm_model    = 발급받은 endpoint ID
    tip_llm_base_url: str = ""
    tip_llm_model: str = ""

    # LLM 호출 온도 — 목적별로 분리한다.
    #   2026-07-30 P1-3 실측으로 확정 (전 과정·수치:
    #   experiments/temp_sweep/결과_20260730_온도스윕.md).
    #
    #   실측의 핵심은 "정확도로는 온도를 고를 수 없다" 였다. 골드셋 정확도는
    #   0.0~0.4 구간에서 평평했고(수집 2%p·evidence 0%p 차이), 같은 설정을 그대로
    #   재실행했을 때의 흔들림이 6~7%p 로 그보다 3배 컸다. 반면 결정성은 온도에
    #   또렷하게 반응했다(같은 입력 5회 완전일치: 0.0 = 100% / 0.2 = 87% / 0.4 = 27%).
    #   → 추출·구조화는 정확도를 잃지 않고 결정성을 얻는 0.0 이 정답이다.
    #     ⚠ 이 값을 올리면 평가 노이즈가 커져 다른 실험의 판정력까지 같이 떨어진다.
    #
    #   ⚠ exaone 호출부(prior 0.2)의 온도는 P2-1 범위라 아직 여기 없다.
    #     마음 재해석 0.3 은 FT 골드셋을 그 온도로 채점해 확정한 값이므로 대상 아님.
    midm_temp_extract: float = 0.0        # extract_answer — 슬롯 추출
    midm_temp_correction: float = 0.0     # extract_correction — 정정 지시 해석
    # 질문 작문은 0.0~0.4 전 구간에서 지표가 평평했다 — 중복질문이 4.75/4.75/4.79 로
    # 사실상 동일해 "온도를 낮추면 질문이 반복된다"는 가설이 반증됐다(중복의 원인은
    # 온도가 아니라 같은 슬롯 재질문 로직). 자연스러움은 이 하네스로 못 재므로
    # 근거 없이 바꾸지 않고 현행값을 유지한다 — 변경하려면 사람 평가가 선행돼야 한다.
    midm_temp_phrase: float = 0.4         # phrase_question — 질문 작문
    # tip 구조화는 확정 모델 Mi:dm 2.0 Mini 로 재측정해 확정했다(2026-07-31).
    #   0.2 가 구체성 균형정확도에서 +1.8~3.1%p 앞섰지만 0.0 을 택했다 — 그 이득은
    #   "하" recall 한 클래스에서 나온 3~4건이고(골드 16건 × 3회), 대가로 결정성이
    #   96.7% → 87% 로 떨어지며 필드추출은 이득이 없다(86.2 / 86.4 / 85.8).
    #   호출 실패도 0.2 에서만 재현됐다(두 번 다 1건) — 실패는 조용한 스텁 폴백이라
    #   그 제보만 키워드 추측으로 처리되고 로그 없이는 안 보인다.
    #   무엇보다 이 등급은 신뢰도 p 의 25%(trust_weight_specificity)로 들어가는
    #   수색 판단 근거다. 같은 제보에 같은 점수가 나오고 사후에 되짚을 수 있어야 한다.
    tip_llm_temp_structure: float = 0.0   # structure_tip — 제보 구조화 + 등급판정

    # Phase 0 축 점수 컴파일 (phase0.axis_scoring) — 골드셋 실험으로 검증된 B×P1 채점.
    # 기본 off: 회의에서 채점 방식 채택 시 켠다. runs = 축당 호출 수(3회 다수결 권장).
    axis_scoring_enabled: bool = False
    # ⚠ 이 값은 축 채점만 쓰는 게 아니다 — behavior_compiler,
    #   env_response_compiler, route_familiarity_compiler 가 같이 읽는다.
    #   이름이 축 채점처럼 보여도 낮추면 네 경로의 다수결이 한꺼번에 꺼진다.
    axis_scoring_runs: int = 3
    # 축 채점(P1) 전용 호출 수 — 0이면 위 공유값을 따른다.
    #   2026-07-28 실측으로 축 채점만 1회로 낮출 근거가 나왔다(골드셋 90셀에서
    #   runs=3·1 정확일치 0.88 동일, 반복 3회 분산 0, 동시성 8에서 30셀 중 1셀만
    #   흔들림 → 기대 손실 0.27%p, 호출 21회 → 7회).
    #   나머지 세 컴파일러는 측정하지 않았으므로 공유값(3)을 그대로 둔다.
    axis_scoring_p1_runs: int = 0
    axis_rubric_path: str = "app/phase0/axis_rubric.md"   # 기준표 단일 소스 (md)
    # 비동기 채점(기본): 보호자의 마지막 확인 응답을 채점(EXAONE 21회, 40초~1분)이
    # 막지 않게 등록을 먼저 확정하고 점수는 백그라운드로 채운다. 테스트·디버깅은 false.
    axis_scoring_async: bool = True
    # stale 채점 마커 재시도 임계(초). IN_PROGRESS 마커가 이 시간보다 오래되면
    # 채점 스레드가 죽은 것으로 보고 다음 신고에서 재채점한다. 살아있는 채점의
    # 최악(healthy-slow, 7축·부하) ~6분에 마진을 둔 값 — 오판 시 이중 EXAONE
    # 호출이 나므로 넉넉히 잡는다. EXAONE 완전 다운 시 이론적 최대(21분)는
    # 결과가 무가치하므로 보호 대상 아님. config 라 운영 데이터로 튜닝 가능.
    axis_scoring_stale_seconds: int = 600

    # Phase 0 온보딩 — 한국어 문장 임베더 (히스토리-어웨어 슬롯 검색용)
    #   embed_base_url 있으면 원격 OpenAI 호환 /embeddings, 없으면 embed_model 을
    #   로컬 sentence-transformers 로 로드. 완전히 비우면 해시 스텁(의미검색 불가).
    #   KURE-v1(bge-m3 기반) — 이전 jhgan/ko-sroberta-multitask 대비 실측 우위:
    #   슬롯 argmax 적중률 75.9%→93.1%, 실 Mi:dm 질문수 168.3→164.2(SD 0.6).
    #   비용: 상주 메모리 +367MB→+1137MB, 쿼리 인코딩 44ms→169ms(LLM 호출에 흡수됨).
    #   ⚠ 이 모델을 바꾸면 retrieval.py 의 절대 임계 3개를 반드시 재보정할 것 —
    #     코사인 분포가 통째로 이동한다(ko-sroberta 기준값을 KURE 에 쓰면 디노이즈가 꺼짐).
    embed_base_url: str = ""
    embed_model: str = "nlpai-lab/KURE-v1"
    embed_api_key: str = ""

    # 축 채점 전용 모델 — 비우면 exaone_model 을 그대로 쓴다.
    #   2026-07-28 실측: 지식 주입 LoRA(exaone-sar)를 전역으로 쓰면 축 채점이
    #   골드셋 정확일치 0.88 → 0.74, κ_qw 0.96 → 0.86 으로 떨어진다.
    #   특히 distress_induced_movement_reactivity 0.86 → 0.29.
    #   학습에 안 쓴 과제가 손상된 것이고 JSON 파싱은 통과하므로 형식 검사로는
    #   안 잡힌다. prior·마음은 파인튜닝본, 축 채점은 base 로 나눈다.
    axis_scoring_model: str = ""

    # 마음 재해석 전용 — 2026-07-30 모델 확정 (근거·전 과정:
    #   experiments/mind_tuning/결과_20260730_행동LoRA_게이트_8셀비교.md).
    #   mind_model: 비우면 exaone_model. 운영 확정값 = "exaone-mind-v5"
    #     (vLLM --lora-modules 이름 — 행동 95%·goal 100%·치명 0).
    #     어댑터는 마음 재해석에만 라우팅한다 — prior(sar)·축 채점(axis) 경로
    #     오적용 금지 (경로 교차 시 형식·성능 손상 실측).
    #   mind_contract: "v2" = 1인칭 행동 계약 + guided decoding (확정 기본) /
    #     "v1" = 분석가형 (롤백용 — 어댑터 없이 base 프롬프트-온리와 짝).
    #   기본값을 확정값으로 명시 — 비워 두면 exaone_model(현 운영값 sar)로
    #   폴백돼 마음 경로가 조용히 오라우팅되는 함정이 있다. 어댑터 미마운트
    #   환경에서는 호출 실패 → 기존 휴리스틱 폴백으로 안전 저하.
    mind_model: str = "exaone-mind-v5"
    mind_contract: str = "v2"

    # RAG — 논문 코퍼스 검색으로 EXAONE 추론에 근거를 붙인다 (P1-4).
    #   인덱스는 sar-finetune/build_rag.py 산출물(npz 한 개: 벡터+메타+임베더명).
    #   임베더는 인덱스에 기록된 것을 따른다(질의·문서 모델이 다르면 검색이 무의미).
    #   rag_max_per_source: 한 논문이 top-k 를 독식하지 못하게 하는 출처당 상한.
    rag_enabled: bool = True
    rag_index_path: str = "data/rag_index.npz"
    rag_top_k: int = 4
    rag_max_per_source: int = 2
    rag_max_chars: int = 1800

    # 카카오 Local API — Phase 0 끌림점 지오코딩(키워드 장소검색으로 건물 단위 POI).
    #   있으면 KakaoGeocoder 우선 사용, 없으면 gazetteer/nominatim 폴백.
    kakao_rest_key: str = ""

    # H3 격자 해상도 (9 ≈ 육각형 변 174m, 도심 수색 단위에 적합)
    h3_resolution: int = 9

    # 도로망 (OSMnx) — Phase 2 시뮬레이션의 "도로 위에서만 이동" 제약
    #   roadnet_preload=True 면 신고 접수(Phase 1) 시 LKP 반경 그래프를 미리 로딩.
    #   테스트·오프라인 환경 기본값은 False (시뮬레이션이 필요할 때 캐시에서 로딩).
    roadnet_preload: bool = False
    roadnet_radius_m: int = 3000            # 아키텍처 문서: LKP 반경 3km (동적 스케일의 하한)
    # P1-3 — 로딩 반경을 프로파일·경과시간의 p90 지원으로 스케일 (radius.roadnet_radius_m).
    #   고정 3km 는 치매 6h 중앙값 3.9km 가 그래프 밖(sim_testset 3h/6h dist_ratio 저하 실측).
    #   반경은 [roadnet_radius_m, roadnet_radius_max_m] 클램프 + 1km 올림 양자화 —
    #   새 반경 첫 로딩은 Overpass 콜드 다운로드(수십 초, 이후 디스크 캐시).
    roadnet_dynamic_radius: bool = True
    roadnet_radius_max_m: int = 6000
    roadnet_cache_dir: str = "data/roadnet_cache"

    # 환경 레이어 — 환경부 EGIS 토지피복지도 WMS (인증키 불필요, 2026-07-11 검증)
    #   케이스 영역 래스터 1회 + 색→클래스 보정 조회 소수로 전 노드 피복 분류.
    egis_wms_url: str = "https://api.mcee.go.kr/geoserver/wms"
    egis_landcover_layer: str = "EGIS:lv3_2021_g"   # 세분류 2021년판

    # 건물 높이 레이어 — OSM height 태그가 없는 건물은 building:levels(층수) *
    # 이 값으로 높이를 근사한다. 국내 층고 통상값(약 3m/층) 기준, 잠정값.
    building_level_height_m: float = 3.0

    # Phase 2 — Monte Carlo
    mc_num_walkers: int = 500      # 두 MC 공통 워커 수 — 보행은 순수 알고리즘이라 공짜
    # 에이전트 MC 의 EXAONE 마음 재해석 실호출 예산 (예측 1회당).
    # 아키텍처 문서의 "비용 고려 10회"를 워커 수 제한이 아니라 LLM 호출 예산으로
    # 재해석 (2026-07-12): 워커 10명의 종착점 히스토그램은 셀당 0.1 단위 분산이
    # α=0.5 가중치를 받는 통계적 결함이었다. 500 워커 전부 걷되, 예산 내 발동만
    # 실호출하고 결과를 풀에 저장 → 이후 발동은 풀에서 독립 표집
    # (결정론적 마음 캐시 금지 — 분포 저장 + 매 진입 독립 표집 원칙).
    # P2-1 budget 스윕 실측(2026-07-31, mind-v5 라이브, experiments/predict_timing/
    # results_20260731_0005): 호출당 ~1.0s 선형, budget 5 = 예측 10.0s(시연 목표선).
    # POA JS(vs budget10)는 5/7/3 전부 run-to-run 노이즈 바닥(0.023) 부근 —
    # 품질 손실 없이 시간만 준다. 시연 기본값 5, 더 조이려면 3까지 실측 근거 있음.
    mind_call_budget: int = 5
    # 워커당 마음 재해석(전환) 최대 횟수 — PR #21 과제3 "다회전환". 1이면 원래
    # 동작(워커당 1회). 2회차부터는 예산과 무관하게 풀 표집만 쓰므로 (실호출
    # 예산 불변) 마음 변화 시퀀스(옛집→혼란→휴식)를 복원하면서 비용은 그대로.
    mind_transitions_per_walker: int = 2
    # 마음 재해석의 behavior(닫힌 4종)를 보행에 반영할지. **기본 꺼짐.**
    #   끔 = 지금까지와 동일하게 confusion·goal_label 만 소비하고 behavior 는 기록만
    #        한다 (기존 측정치 — 알림셀 0.5h 11 · 1h 22 · 2h 31 · 4h 40, 봉인 test
    #        수치 — 가 그대로 유효).
    #   켬 = 아래 매핑 적용. 각 근거는 simulation.py 의 해당 분기 주석에 있다.
    #        귀소 시도  → 과거 거주지·직장 방위로 걷되 도달 판정 없음 (DEM-31·DEM-34).
    #                     과거 장소가 등록돼 있지 않으면 **매핑하지 않는다**.
    #        계속 배회  → 목표 해제 후 매 스텝 무작위 방위 (DEM-33 random 정의).
    #        은신·멈춤  → 그 자리에서 이동 종료 (DEM-31 26% 근거리 정지 발견).
    #        끌림점 접근 → goal_label 경로가 이미 처리 (모드 해제만).
    # ⚠ 켜면 종착 분포가 달라져 위 실측값 전부 재측정 대상이 된다. 봉인 test 96콜의
    #   행동 분포가 끌림점 접근 71 / 계속 배회 9 / 은신·멈춤 8 / 귀소 시도 8 이므로
    #   새 경로가 뜨는 비율은 26%이고, 소비 단위가 mind_call_budget(=5) 짜리 풀
    #   표집이라 예측 간 분산이 크다. 효과 판정은 평가 하네스(발견율 대 알림 셀 수
    #   곡선) 완성 후에 한다 — JS divergence 는 "달라졌다"만 말하고 "나아졌다"를
    #   말하지 못한다.
    mind_behavior_enabled: bool = False
    # 도로 위계 선호(gauges._ROAD_PREFERENCE)의 세기 — 지수로 들어간다.
    # 0=끔(전부 중립), 1=표 그대로, 2=대비 강화. 평가 하네스 그리드서치용
    # 단일 노브. 치매에만 적용(문헌 근거 범위).
    road_preference_strength: float = 1.0
    # 개인 환경 반응(EnvResponse)이 이동 확률을 기울이는 세기. 0=끔.
    # 축 기준표에 없는 개인 특성("물가만 보면 다가간다")의 소비 강도 —
    # 평가 하네스가 개인화 기여도를 재는 ablation 노브.
    env_response_strength: float = 1.0
    # 시뮬레이션이 도로망 그래프를 쓸지 — 켜면 Phase 2 실행 시 LKP 반경 도로망을
    # 로딩(캐시 우선, 실패 시 연속 공간 폴백). 오프라인 테스트 기본값은 False.
    use_roadnet: bool = False

    # Phase 3 — 제보 판정 임계값 (예시값, 시뮬레이션 테스트로 튜닝 대상)
    tip_discard_threshold: float = 0.2   # p < 0.2 → 파기
    tip_lkp_threshold: float = 0.8       # p ≥ 0.8 + 위치·시각 특정 → 층2 트리거

    # Phase 3 — 층2(Phase 2 재실행) 트리거
    layer2_periodic_minutes: int = 45    # 주기 재실행 (Koester 반경 확장 대응, 30~60분)
    kl_divergence_threshold: float = 0.5 # posterior가 baseline에서 이탈했다고 보는 KL 임계

    # Phase 3 — D3(3차 알림, 새 지역 한정) — JS는 예비스크린, 집합차+질량임계가 최종판정.
    # new_region_mass_threshold 는 새 셀 "하나"가 아니라 새 셀 전체 합산 질량 기준
    # (셀 단위로 재면 넓게 퍼지는 실제 분포에서 항상 무반응이라 D3 의 존재 이유와
    # 모순됨 — 실측으로 확인됨). 두 값 모두 완전 잠정 — 팀 확인 필요(작업6 설계 노션 문서 참고)
    js_divergence_threshold: float = 0.05
    new_region_mass_threshold: float = 0.05

    # 층1 혼합 likelihood 커널
    likelihood_l_max: float = 5.0        # 목격 지점 셀의 L
    likelihood_l_far: float = 0.1        # 먼 셀의 L (음의 증거)
    likelihood_sigma_cells: float = 2.0  # 가우시안 감쇠 폭 (H3 grid distance 단위)

    # 1차 안전반경 (Reflex Tasking, Koester) — 신고 직후 POA 없이 IPP 주변
    # k-ring 즉시 알림. 아키텍처 문서: "예측 위치(육각 격자) + 한두 칸".
    # res9 셀 중심 간격 ≈ 300m → k=2 ≈ 반경 600m, 19셀. 수색 초반에는
    # 확률 분석보다 즉시 확인이 중요하다는 원칙 — Phase 2 완료 후 POA 알림으로 전환.
    reflex_kring: int = 2
    reflex_alert_on_intake: bool = True   # 신고 접수 시 자동 발송 (실패해도 접수 계속)

    # 알림 발송 — POA 상위 셀 누적 커버리지
    alert_coverage: float = 0.8
    # 알림 셀 수 상한 (타겟팅 가드레일) — 꼬리가 두꺼운 분포에서 80% 커버리지가
    # 수천 셀(사실상 무차별)로 폭주하는 것을 차단. res9 셀 ≈0.105km² 기준
    # 500셀 ≈ 52km². 건강한 케이스(경과 1h)는 80% 도달에 ~159셀이라 안 걸린다.
    # 값은 잠정 — 실제 알림 로그 쌓이면 평가곡선(알림수 vs 발견율)으로 튜닝 대상.
    max_alert_cells: int = 500

    # ── Phase 3 제보 신뢰도 p (docs: "제보 신뢰도 p 계산 방식") ─────────
    # p = 가중평균(시공간개연성·구체성). 없는 신호는 가중치 재정규화.
    # r = plausibility/specificity 비율만 결과에 영향(재정규화 구조, 절대값 무의미).
    # P1-5 실험(2026-07-31, experiments/trust_weight/)으로 r=1.6(구설정 0.40/0.25) → r=2.3
    # 확정. ★핵심 근거는 진짜/가짜 목격담 ROC-AUC 분리 실험(run_auc_sweep.py, 판단 개입 없이
    # 좌표 생성규칙만으로 정답 결정) — gold/Mi:dm실측 두 스테이지 모두 r≈2.1~2.2부터
    # AUC=1.0(완벽분리) 도달. 정책판단 기반 정답표 스윕(run_sweep.py, 사람이 만든 정답표라
    # 순환논리 위험 있음 — 보조 근거)도 별도로 r=2.3 최고점(85.7%/78.6%, 현행1.6은
    # 72.9%/67.1%)으로 독립 수렴, 교차검증됨. specificity 값은 그대로 두고 plausibility 만
    # 올려 비율 맞춤(0.575/0.25=2.3).
    trust_weight_plausibility: float = 0.575  # 시공간 개연성 (kinematic, 알고리즘)
    trust_weight_specificity: float = 0.25    # 구체성 (제보 구조화 LLM, tip_llm)
    trust_base_p: float = 0.3                 # 아무 신호도 없을 때의 사전 신뢰

    # kinematic 상한 — v_max(km/h) × Δt = 도달 가능 반경. 넘으면 지수 감쇠.
    #
    # v_max 의 정의: "여러 시간에 걸쳐 이동할 때 낼 수 있는 최대 속도"(짧은 거리 순간
    # 최고속이 아님). 소프트 경계(초과 시 지수감쇠)+통계 p95 로 이중 상한이라, 실종자를
    # 놓치지 않도록 관대한 쪽으로 잡되, 비장애 일반 성인 fast 를 넘지 않게 sanity 상한을 둔다.
    # 문헌 근거(2026-07-29 확정):
    #
    # ▷ 치매 4.32km/h — 치매 특정 최대속도는 문헌 공백(관련 논문이 페이월). 치매 유병은 대부분
    #   고령이므로 건강 고령자 "서둘러" 상한으로 대체한다: 고령자의 73.8% 가 서둘러 걸어도
    #   1.2 m/s(=4.32km/h)를 못 넘는다(PLOS ONE 2017, PMC5536437). 실제 치매 환자는 건강
    #   고령자보다 더 느리므로(국내 치매 comfortable 0.76 m/s=2.74km/h, Lee 2020) 4.32 는
    #   치매에게 넉넉한 안전측 상한 — 놓침 방지 방향으로 정당.
    #
    # ▷ 지적장애 5.0km/h — 후보였던 고령 ID fast 6.5(Oppewal&Hilgenkamp 2019)는 GAITRite
    #   짧은 매트에서 잰 "순간 최고속"이라 몇 시간 지속 이동의 v_max 로는 과대추정이다(건강
    #   일반 성인 fast 중앙값 5.58km/h 보다도 높아 비상식적 — 운동기능 손상 집단이 비장애인보다
    #   빠를 수 없다). 지속 보행 근거들은 4.3~5.6km/h 구간을 지지한다: ID comfortable 4.26
    #   (Oppewal 2018, PMC7540034 — 구간 하한 근처) · 다운증후군 청년 6분보행 4.36km/h
    #   (436m/6min, Springer 2018 — DS 는 근긴장 저하로 더 느린 하위유형이라 일반 ID 의 하한) ·
    #   건강 성인 fast 중앙값 5.58km/h(구간 상한). 이 구간의 둥근 대표값으로 5.0 채택 — 비장애인
    #   보다 빠르지 않고(상식 부합) ID comfortable 은 초과(서두름 반영). 결과적으로 기존 상수
    #   5.0 이 사후 문헌 근거로 방어됨.
    #
    # ※ 정밀도 주의: v_max 는 하드컷이 아니라 초과 시 지수감쇠 + 통계 p95 이중 상한이라, 위
    #   구간(4.3~5.6) 안에서 소수점 값 차이는 결과에 거의 영향이 없다. 핵심은 임의값을 인용
    #   가능한 문헌 구간으로 교체한 "근거 확보"이지 4% 수준의 수치 정확도 개선이 아니다.
    #
    # 전부 도보 기준(2026-07-24 안1 — 대중교통 미반영).
    reach_vmax_dementia_kmh: float = 4.32
    reach_vmax_id_kmh: float = 5.0
    reach_min_dt_hours: float = 0.05         # Δt 하한 — 0 나누기·동시목격 방지
    # 초과거리 감쇠 계수 — plausibility() 의 exp(-k·(d-d_max)/d_max). 1.0 = 기존 암묵값.
    # 값이 클수록 d_max 를 살짝만 넘어도 급감쇠(엄격), 작을수록 완만(관대). P1-6 튜닝 대상.
    reach_decay_k: float = 1.0

    # ── 개인정보 파기 (개인정보 보호법 §21 + 표준 개인정보 보호지침) ─────
    # 종결(발견/철회) 후 이 일수가 지나면 purge_expired 가 케이스를 파기한다.
    # 5일 = 표준지침의 "정당한 사유가 없는 한 5일 이내" 상한. 유예를 두는
    # 이유는 오종결 복구·재실종 초동 대응. 즉시 파기는 명시 삭제요청
    # (DELETE /privacy/...)으로 언제든 가능.
    privacy_retention_days: int = 5
    # 미완료 인터뷰 세션 방치 상한 — persona_id 가 없어 보호자 삭제요청으로
    # 못 지우는 draft 개인정보를 시간 상한으로 파기 (인증 도입 전 임시 방어)
    privacy_session_ttl_hours: int = 48
    # 감사로그 영속 파일 (JSONL append-only) — 인메모리 storage 는 재시작 시
    # 증발하므로 파기 증적만은 파일로 남긴다. DB 전환 시 테이블로 임포트.
    privacy_audit_path: str = "data/audit_log.jsonl"


settings = Settings()
