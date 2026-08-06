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

    # Phase 3 수색 안내 문구 다듬기 전용 — **Mi:dm 2.0 Mini**(2026-08-06 결정,
    # 근거는 llm/copy_llm.py). 비우면 tip_llm_* 를 그대로 물려받는데, 그게 곧
    # mini 를 쓴다는 뜻이다 — 한 문장 어조를 다듬는 일이라 경량 모델로 충분하고,
    # 온보딩 대화용 Mi:dm(midm_*)까지 끌어올 이유가 없다.
    # 모델을 갈아끼워 비교할 때만 채운다.
    copy_llm_api_key: str = ""
    copy_llm_base_url: str = ""
    copy_llm_model: str = ""

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
    # 안내 문구 다듬기 — 2026-08-06 Mi:dm Mini 실측으로 확정 (4케이스 × 10회).
    #   통과율(볼 곳·회피 지시가 살아남은 비율): 0.4 = 82% / 0.2 = 100% / 0.0 = 100%
    # 거절되면 템플릿으로 안전하게 물러나므로 위험하진 않지만, 0.4 는 다섯 번에
    # 한 번꼴로 LLM 을 붙인 의미가 사라진다("나무가 우거진 곳을 중심으로" — 볼 곳
    # 셋이 통째로 빠진 실제 출력).
    #
    # 낮춰도 문구가 딱딱해지지 않는다는 것을 눈으로 확인했다 — 0.0 과 0.4 출력이
    # 사실상 같았다. **다듬은 문구는 사건당 한 번만 만들어 캐시하므로**(storytelling)
    # 표본 다양성이 사용자에게 주는 이득이 애초에 없다.
    # 0.0 을 더 내리지 않은 이유: 0.2 대비 측정 이득이 없고, vLLM 연속 배칭에서는
    # 0.0 도 완전 결정론이 아니라 "결정성"을 근거로 삼을 수 없다.
    # ⚠ 초기 기획안의 0.7 은 실측 근거가 없어 채택하지 않았다.
    copy_llm_temp: float = 0.2

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
    # 비동기 채점(기본): 보호자의 마지막 확인 응답을 채점(EXAONE 18회 = 치매 6축
    # × 3회, 40초~1분)이 막지 않게 등록을 먼저 확정하고 점수는 백그라운드로
    # 채운다. 테스트·디버깅은 false.
    #   호출 수는 axis_rubric.md 에 있는 축만 센다(scored_axes 가 기준표에 없는
    #   축을 자동 제외). 치매 단독 스코프(2026-08-03)로 발달장애 4축이 기준표에서
    #   빠져 7축 21회 → 6축 18회가 됐다. 위 74~77행의 "21회 → 7회"는 그 이전
    #   7축 기준으로 잰 값이라 지금은 18회 → 6회로 읽어야 한다.
    axis_scoring_async: bool = True
    # stale 채점 마커 재시도 임계(초). IN_PROGRESS 마커가 이 시간보다 오래되면
    # 채점 스레드가 죽은 것으로 보고 다음 신고에서 재채점한다. 살아있는 채점의
    # 최악(healthy-slow, 7축·부하) ~6분에 마진을 둔 값 — 오판 시 이중 EXAONE
    # 호출이 나므로 넉넉히 잡는다. EXAONE 완전 다운 시 이론적 최대(21분)는
    # 결과가 무가치하므로 보호 대상 아님. config 라 운영 데이터로 튜닝 가능.
    axis_scoring_stale_seconds: int = 600

    # Phase 0 온보딩 — 한국어 문장 임베더 (히스토리-어웨어 슬롯 검색용)
    #   embed_base_url 있으면 원격 OpenAI 호환 /embeddings, 없으면 embed_model 을
    #   로컬 sentence-transformers 로 로드. 완전히 비우면 해시 스텁(의미검색 불가) —
    #   .env 미설정 시의 안전한 기본값. 실제 값은 .env 에서 채운다(현재 Upstage).
    #   ⚠ 임베더를 바꾸면 retrieval.py 의 절대 임계 3개를 반드시 재보정할 것 —
    #     코사인 분포가 통째로 이동해서, 이전 임베더 기준값을 그대로 쓰면 가드가 무력화된다.
    embed_base_url: str = ""
    embed_model: str = ""
    embed_api_key: str = ""
    # API 임베더 중 query/passage 를 별도 모델로 받는 곳(예: Upstage embedding-query
    # vs embedding-passage)용 — 비우면 embed_model 을 그대로 양쪽에 쓴다. 로컬
    # 임베더는 이 구분이 없어 무시된다.
    embed_model_passage: str = ""

    # 축 채점 전용 모델 — 비우면 exaone_model 을 그대로 쓴다.
    #   2026-07-28 실측: 지식 주입 LoRA(exaone-sar)를 전역으로 쓰면 축 채점이
    #   골드셋 정확일치 0.88 → 0.74, κ_qw 0.96 → 0.86 으로 떨어진다.
    #   특히 distress_induced_movement_reactivity 0.86 → 0.29.
    #   학습에 안 쓴 과제가 손상된 것이고 JSON 파싱은 통과하므로 형식 검사로는
    #   안 잡힌다. prior·마음은 파인튜닝본, 축 채점은 base 로 나눈다.
    axis_scoring_model: str = ""

    # 마음 재해석 전용 — 2026-08-04 치매 단독 재학습본으로 교체.
    #   mind_model: 비우면 exaone_model. 운영 확정값 = "exaone-mind-dem3"
    #     (vLLM --lora-modules 이름). 봉인 test 144회 실측: 행동 98%·목표 89%·
    #     혼란도 88%·치명 0·어휘 밖 0 (experiments/mind_goldset/results 의
    #     goldset_eval_test_..._exaone-mind-dem3_20260804_113144).
    #   종전 exaone-mind-v5 는 **치매+발달장애 혼합 데이터** 학습본이다. 대상을
    #     치매로 좁히면서(2026-08-03) 학습 데이터를 치매만으로 다시 만들고
    #     (행동 진술 33→73건) dem-e1→dem2→dem3→dem4 를 학습했다. dem4 는 개발용
    #     점수가 일부 더 높으나 **봉인을 열지 않았다** — 봉인은 모델 확정 후 단 1회
    #     규칙이라 점수가 좋다고 다시 열면 시험지 자격이 사라진다. 그래서 봉인으로
    #     검증된 dem3 가 확정본이다.
    #   어댑터는 마음 재해석에만 라우팅한다 — prior(sar)·축 채점(axis) 경로
    #     오적용 금지 (경로 교차 시 형식·성능 손상 실측).
    #   mind_contract: "v2" = 1인칭 행동 계약 + guided decoding (확정 기본) /
    #     "v1" = 분석가형 (롤백용 — 어댑터 없이 base 프롬프트-온리와 짝).
    #   기본값을 확정값으로 명시 — 비워 두면 exaone_model(현 운영값 sar)로
    #   폴백돼 마음 경로가 조용히 오라우팅되는 함정이 있다. 어댑터 미마운트
    #   환경에서는 호출 실패 → 기존 휴리스틱 폴백으로 안전 저하.
    mind_model: str = "exaone-mind-dem3"
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
    # 예산을 **어디에** 쓰는가 (2026-08-05 층화 배분). 구버전은 도착 순서대로 줬고,
    # 그 결과 실호출의 100% 가 1회차 전환에서만 일어났다(소비의 38~42% 는 2회차).
    # 효과 귀속(n12 실측): 미커버 축의 개선은 거의 전부 "회차 게이트 제거" 몫이고,
    # 층화 고유 기여는 꼬리 층 보장이다 — "불안 층 실호출 0건" seed 42% → 0%
    # (게이트만 제거하면 67% 로 악화). 상세는 simulation.py _MindPool 독스트링.
    # ⚠ "예산 크기가 아니라 배분 문제"라고 쓰지 말 것 — 그 결론을 낳은 스윕은
    # 구버전 결함이 지표 바닥을 박아놓은 조건에서 돌았다(같은 독스트링 참조).
    #
    # 재사용 표집의 문맥 매칭 세기 λ. w = exp(-λ·층거리).
    #   0   = 구버전(문맥 무관 균등 표집) — ablation 끔 상태이자 회귀 기준선
    #   1.0 = 기본. 무한대(하드 매칭)로 두지 않는 이유: 층당 엔트리 1개일 때
    #         하드 매칭은 사실상 결정론적 마음 캐시가 되어 "분포 저장 + 매 진입
    #         독립 표집" 원칙을 깬다. 유한 λ 는 기대값만 문맥에 맞춘다.
    mind_pool_match_strength: float = 1.0
    # 나타나지 않은 층의 전용 쿼터를 공용 예비로 회수하는 워커 진행률.
    # 워커가 i.i.d. 라 층 도착은 정상과정이다 — 임계 이후까지 안 나타난 층을 계속
    # 기다리면 얻는 것은 거의 없고 남은 워커가 쓸 풀만 얇아진다.
    mind_pool_release_p: float = 0.15
    # 회수된 예비를 "이미 대표가 있는 층의 2번째 표본"에도 허용하는 진행률.
    # 이 임계 전에는 예비를 미커버 층에만 준다(빈발 층이 예비를 먼저 삼키는 것 방지).
    mind_pool_widen_p: float = 0.35
    # 워커당 마음 재해석(전환) 최대 횟수 — PR #21 과제3 "다회전환". 1이면 원래
    # 동작(워커당 1회). 2회차 이상은 층 ("later",) 로 묶여 예산 경쟁에 참여한다
    # (구버전은 2회차의 실호출 확률이 구조적으로 0이었다 — 위 층화 주석 참조).
    mind_transitions_per_walker: int = 2
    # 마음 재해석의 behavior(닫힌 4종)를 보행에 반영할지. **2026-08-04 기본 켜짐.**
    #   끔 = confusion·goal_label 만 소비하고 behavior 는 기록만 한다 (구 기본값).
    #   켬 = 아래 매핑 적용. 각 근거는 simulation.py 의 해당 분기 주석에 있다.
    #        귀소 시도  → 과거 거주지·직장 방위로 걷되 도달 판정 없음 (DEM-31·DEM-34).
    #                     과거 장소가 등록돼 있지 않으면 **매핑하지 않는다**.
    #        계속 배회  → 목표 해제 후 매 스텝 무작위 방위 (DEM-33 random 정의).
    #        은신·멈춤  → 그 자리에서 이동 종료 (DEM-31 26% 근거리 정지 발견).
    #        끌림점 접근 → goal_label 경로가 이미 처리 (모드 해제만).
    #   전환 근거(2026-08-04 채널별 ablation, 500워커×seed5, 정릉 3km): behavior 를
    #   버리면 마음 모델이 최종 POA 에 남기는 기여가 goal_label 하나로 줄고,
    #   confusion 은 κ 경유로는 seed 노이즈에 묻힌다(극단 대비 1.12배). 생성만 하고
    #   소비하지 않는 필드를 계약에 남겨 두는 쪽이 더 큰 비용이라 판단해 켠다.
    # 알림셀 기준선은 **experiments/alert_cells/** 로 옮겼다(2026-08-04 사용자 결정).
    #   종전 주석값(0.5h 11 · 1h 22 · 2h 31 · 4h 40)은 재현 스크립트가 없어 조건을
    #   확인할 수 없었고 재현도 안 돼 폐기했다. 새 기준선(seed 12개, 평균±표준오차):
    #     A 끔    12.2±0.18 / 13.9±0.38 / 15.3±0.45 / 15.8±0.37
    #     D 기본  11.2±0.17 / 11.8±0.24 / 12.4±0.45 / 13.5±0.52   (0.5h/1h/2h/4h)
    #   결론: **개인화를 기반으로 수색 구역을 좁힌다.** 4h 기준 알림 셀 15.8 → 13.5
    #   (약 15% 감소, 오차 밖). 좁아지는 방식은 확률이 더 뭉치는 것이다 — 최고 칸
    #   23.5%→24.5%, 평탄도 8.2→6.3(알림 셀 하나하나가 두툼해졌다는 뜻).
    #   참고로 평균 이탈거리는 구성과 무관하다(0.57→0.55km). 후보 지역의 물리적
    #   크기는 Koester p95·물리 상한이 정하고, 마음 모델은 그 안에서 우선순위를
    #   만든다. 즉 "덜 뒤져도 되게" 하는 것이지 "덜 멀리 갔다고 보는" 것이 아니다.
    #   ⚠ 지표상으로는 B(behavior 만)가 D 보다 낫다(셀 11.9 · 최고 칸 25.8%). 그래도
    #     D 를 쓰는 이유는 이 지표들이 "더 잘 찾는가"를 못 재기 때문이다 — 잴 수 없는
    #     것의 대리 지표에 맞춰 문헌 근거 있는 채널을 끄는 것은 국소 최적화다.
    #     B vs D 판정은 발견율 대 알림 셀 수 곡선이 생긴 뒤로 미룬다.
    #   ⚠ seed 3개 판(오차 ±2셀)에서 "시간 평평"·"behavior 가 좁힌다"를 두 번 잘못
    #     읽었다. n≥12 로 재고 1셀 이하 차이는 인용하지 않는다.
    mind_behavior_enabled: bool = True
    # 혼란도 → 목적지 인식 실패의 세기 (0=끔, 1=혼란도 그대로 실패확률).
    # 근거: CLM-0023(DEM-34 p6) "목적지를 지나친 뒤 반대 방향에서 접근하면 알아보지
    #   못할 수 있다" + CLM-0015(DEM-31 p6) "길찾기 오류를 스스로 회복하지 못한다".
    #   κ(각도 분산)와 달리 이 경로는 집계 POA 를 실제로 움직인다 — 위 ablation 에서
    #   목표(goal) 채널만 coverage80 을 15.6→8.2 로 옮겼다.
    # ⚠ 계수 자체는 잠정값이다. 인식 실패율을 보고한 연구가 코퍼스 13편에 없어
    #   "혼란도를 그대로 실패확률로 읽는다"는 최소가정을 쓴다(docs/혼란도_수치_근거
    #   _정리.md 2절과 같은 지위). 최적값 주장 금지 — 민감도 노브로만 쓴다.
    confusion_miss_strength: float = 1.0
    # 도로 위계 선호(gauges._ROAD_PREFERENCE)의 세기 — 지수로 들어간다.
    # 0=끔(전부 중립), 1=표 그대로, 2=대비 강화. 평가 하네스 그리드서치용
    # 단일 노브. 치매에만 적용(문헌 근거 범위).
    road_preference_strength: float = 1.0
    # 개인 환경 반응(EnvResponse)이 이동 확률을 기울이는 세기. 0=끔.
    # 축 기준표에 없는 개인 특성("물가만 보면 다가간다")의 소비 강도 —
    # 평가 하네스가 개인화 기여도를 재는 ablation 노브.
    env_response_strength: float = 1.0
    # 시뮬레이션이 도로망 그래프를 쓸지 — 켜면 Phase 2 실행 시 LKP 반경 도로망을
    # 로딩(캐시 우선, 실패 시 연속 공간 폴백). 테스트는 conftest.py 가 항상 "false"로
    # 강제하므로 이 기본값과 무관하게 오프라인이다. 켜진 채 실서비스 기본값 —
    # 캐시 없는 좌표의 첫 요청은 Overpass 콜드 다운로드로 15~110초 걸릴 수 있다
    # (실측, 2026-08-05). CI 파이프라인이 없어 자동화에 영향은 없다.
    use_roadnet: bool = True

    # Phase 3 — 제보 판정 임계값 (예시값, 시뮬레이션 테스트로 튜닝 대상)
    tip_discard_threshold: float = 0.2   # p < 0.2 → 파기
    tip_lkp_threshold: float = 0.8       # p ≥ 0.8 + 위치·시각 특정 → 층2 트리거

    # Phase 3 — 층2(Phase 2 재실행) 트리거
    layer2_periodic_minutes: int = 45    # 주기 재실행 (Koester 반경 확장 대응, 30~60분)
    # POA 자동 갱신 — 위 트리거를 **주기적으로 물어보는** 백그라운드 루프.
    # 판정 로직은 예전부터 있었지만 호출하는 쪽이 없어서, 신고 시점 지도가 수색
    # 내내 그대로 남았다(5시간 실종 신고 → 7시간이 돼도 5시간 지도).
    # 검사 주기와 재실행 주기는 다르다: 자주 묻고(5분) 가끔 돌린다(45분) —
    # 판정은 싸고 예측은 비싸다(EXAONE 5호출).
    poa_refresh_enabled: bool = True
    poa_refresh_interval_seconds: float = 300.0
    kl_divergence_threshold: float = 0.5 # posterior가 baseline에서 이탈했다고 보는 KL 임계

    # Phase 3 — D3(3차 알림, 새 지역 한정) — JS는 예비스크린, 집합차+질량임계가 최종판정.
    # new_region_mass_threshold 는 새 셀 "하나"가 아니라 새 셀 전체 합산 질량 기준
    # (셀 단위로 재면 넓게 퍼지는 실제 분포에서 항상 무반응이라 D3 의 존재 이유와
    # 모순됨 — 실측으로 확인됨).
    #
    # 값 근거 (PR#87, experiments/d3_threshold/, 3,800개 합성 타임라인 결정표):
    #   목표 탐지율 95% · baseline 제보 혼합(고신뢰30/저신뢰50/허위20)의 동작점 채택.
    #   그 행이 mass_thr=0.0664 · js_thr=0.0617 이며 이때 헛알림율 25.9%,
    #   놓침(임계탓) 42/3800. 95%를 고른 이유: 결정표에서 mass_thr 가 가장 높은
    #   (=가장 보수적) 행이라 헛알림이 최소고, 스텁 실험이 낙관했을 수 있는
    #   "허위 제보의 층2 오도달"이 실호출에서 늘어나도 이미 흡수돼 있다.
    #   js_thr 는 결정권이 아니라 "mass 가 발송 판정한 케이스를 하나도 안 거르는
    #   최댓값"으로 따로 산출된 예비 게이트 값이다(mass 보다 항상 헐거움).
    #   ⚠ 전제 2가지: (1) baseline 혼합을 가정한 값 — 실제 제보가 부실하면
    #     (low_quality 환경) 더 낮은 문턱(~0.033)이 필요하다. (2) 구체성 판정은
    #     tip_llm 스텁을 우회해 직접 주입한 상한선 결과 — 실호출 파일럿 재확인은
    #     미실시(P2-D3-2 설계 있음). 운영 알림 로그가 쌓이면 실제 제보 환경으로 재보정.
    js_divergence_threshold: float = 0.0617
    new_region_mass_threshold: float = 0.0664

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

    # ── Phase 3 익명 동시 참여자 수(presence) ────────────────────────
    # TTL 은 프론트 폴링 주기(30s)의 3배 — 한두 번 놓쳐도(터널·일시 오프라인)
    # 참여자가 깜빡이며 사라지지 않게 하는 여유. 늘리면 이탈이 늦게 반영되고
    # 줄이면 카운트가 불안정해진다.
    presence_ttl_sec: float = 90.0
    presence_max_tokens_per_case: int = 10_000  # 메모리 상한 (자세한 근거: presence.py)

    # ── 푸시 발송 (Expo Push Service) ──────────────────────────────
    # 기본값 False = 스텁 모드: 네트워크를 타지 않고 결정적 응답. 테스트가 외부
    # 서비스에 의존하지 않게 하는 장치이자 크레덴셜 없이 파이프라인을 돌리기 위한 것.
    # 실발송하려면 True + Expo 프로젝트에 FCM V1 크레덴셜(서비스 계정) 등록 필요.
    push_enabled: bool = False
    # 선택이지만 권장 — 없으면 남이 우리 프로젝트 이름으로 발송할 수 있다.
    expo_access_token: str = ""
    # 골든타임 알림이라 오래 매달리면 안 된다. 실패해도 접수·예측은 계속돼야 하므로
    # 짧게 끊고 넘어간다.
    push_timeout_sec: float = 10.0
    # 발송 대상 판정 해상도 — 폰이 자기 위치를 이 해상도의 H3 셀 하나로 바꿔
    # 보고하고, 서버는 예측 셀(res9)의 이 해상도 부모와 대조한다.
    #   res7 ≈ 5km². 예측 구역(실측 17km²)을 구분하기엔 충분하고 개인 위치는
    #   안 드러난다 — "목적에 필요한 최소 해상도"가 선택 기준(2026-08-05 확정).
    #   ⚠️ 낮추면(res5·res6) 낭비 발송이 급증하고, 높이면(res8·res9) 사실상
    #     좌표가 되어 최소성 논거가 무너진다.
    push_target_res: int = 7
    # 참여도 등급별 발송 확률 문턱 — **프론트 utils/alertBudget.ts 의
    # PROB_THRESHOLD 와 값이 같아야 한다**(서버·앱이 다르면 사용자는 "알림은
    # 왔는데 앱은 구역 밖이라 한다" 같은 모순을 본다).
    # 기준은 히트맵 상대 스케일(최고 셀 대비) — 근거는 alerts.relative_prob_by_parent.
    push_prob_threshold: dict[str, float] = {
        "high": 0.3,     # 덜 확실한 곳까지
        "normal": 0.45,
        "low": 0.6,      # 확실한 곳만
    }
    # 실종 경과가 이 시간 안이면 경보를 critical(빨강), 넘으면 active(앰버)로
    # 내려준다. 프론트 queries.ts 의 GOLDEN_WINDOW_MS(1시간)와 같은 창 —
    # 화면 카운트다운과 색이 따로 놀면 "긴급이라면서 앰버"가 된다.
    alert_critical_window_h: float = 1.0

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
    # ※ 정밀도 주의: v_max 는 하드컷이 아니라 초과 시 지수감쇠 + 통계 p95 이중 상한이라
    #   소수점 값 차이는 결과에 거의 영향이 없다. 핵심은 임의값을 인용 가능한 문헌
    #   근거로 교체한 "근거 확보"이지 수치 정확도 개선이 아니다.
    #
    # 전부 도보 기준(2026-07-24 안1 — 대중교통 미반영).
    reach_vmax_dementia_kmh: float = 4.32
    reach_min_dt_hours: float = 0.05         # Δt 하한 — 0 나누기·동시목격 방지
    # 초과거리 감쇠 계수 — plausibility() 의 exp(-k·(d-d_max)/d_max). 1.0 = 기존 암묵값.
    # 값이 클수록 d_max 를 살짝만 넘어도 급감쇠(엄격), 작을수록 완만(관대). P1-6 튜닝 대상.
    reach_decay_k: float = 1.0

    # 데모 시드(정릉동 김순자, case-jeongneung-001)를 기동 시 만들지.
    # **영속화가 붙은 뒤로는 기본 꺼짐** — 껐다 켜도 실제 등록분이 남으므로 시드가
    # 필요 없고, 오히려 시연·검증에서 진짜 사건과 섞여 혼선을 준다(2026-08-05:
    # 경보 관문이 새 신고 대신 시드 케이스를 잡았다). 빈 서버에서 앱 화면을 보고
    # 싶을 때만 켠다.
    seed_demo_data: bool = False

    # ── 저장소 영속화 ───────────────────────────────────────────────
    # 켜면 페르소나·인터뷰·케이스가 SQLite 파일에 남아 재시작을 견딘다.
    # **이 서비스의 전제가 영속성이다** — 사전등록은 평시에 하고 실종은 몇 달 뒤에
    # 일어난다. 꺼 두면 서버 재시작 한 번에 보호자가 등록한 것이 전부 사라진다.
    #
    # ⚠ 켜는 순간 "발견 즉시 파기"가 공짜가 아니게 된다. 메모리일 때는 프로세스가
    #   죽으면 자동으로 사라졌지만, 디스크에 쓰기 시작하면 파기가 실제로 파일까지
    #   닿아야 한다. storage.delete() + storage.vacuum() 이 그 경로이고,
    #   tests/test_storage_persist.py 가 파일을 바이너리로 열어 검증한다.
    #
    # 테스트는 conftest.py 가 항상 "false" 로 강제한다 — 테스트가 서로의 디스크
    # 상태를 오염시키면 실행 순서에 따라 결과가 바뀐다.
    persist_storage: bool = True
    storage_db_path: str = "data/storage.db"

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
