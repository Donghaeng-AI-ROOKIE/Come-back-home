"""전역 설정. .env 로 오버라이드 가능 (.env.example 참고)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # 모델 API 키 — 비어 있으면 해당 클라이언트는 스텁 모드
    exaone_api_key: str = ""
    midm_api_key: str = ""
    varco_api_key: str = ""
    upstage_api_key: str = ""

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

    # Phase 0 온보딩 — 한국어 문장 임베더 (히스토리-어웨어 슬롯 검색용)
    #   embed_base_url 있으면 원격 OpenAI 호환 /embeddings, 없으면 embed_model 을
    #   로컬 sentence-transformers 로 로드. 완전히 비우면 해시 스텁(의미검색 불가).
    #   기본 = 가벼운 한국어 STS 모델. 품질 업그레이드: nlpai-lab/KURE-v1 (bge-m3 기반, ~2.2GB).
    embed_base_url: str = ""
    embed_model: str = "jhgan/ko-sroberta-multitask"
    embed_api_key: str = ""

    # 카카오 Local API — Phase 0 끌림점 지오코딩(키워드 장소검색으로 건물 단위 POI).
    #   있으면 KakaoGeocoder 우선 사용, 없으면 gazetteer/nominatim 폴백.
    kakao_rest_key: str = ""

    # H3 격자 해상도 (9 ≈ 육각형 변 174m, 도심 수색 단위에 적합)
    h3_resolution: int = 9

    # 도로망 (OSMnx) — Phase 2 시뮬레이션의 "도로 위에서만 이동" 제약
    #   roadnet_preload=True 면 신고 접수(Phase 1) 시 LKP 반경 그래프를 미리 로딩.
    #   테스트·오프라인 환경 기본값은 False (시뮬레이션이 필요할 때 캐시에서 로딩).
    roadnet_preload: bool = False
    roadnet_radius_m: int = 3000            # 아키텍처 문서: LKP 반경 3km
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
    mind_call_budget: int = 10
    # 시뮬레이션이 도로망 그래프를 쓸지 — 켜면 Phase 2 실행 시 LKP 반경 도로망을
    # 로딩(캐시 우선, 실패 시 연속 공간 폴백). 오프라인 테스트 기본값은 False.
    use_roadnet: bool = False

    # Phase 3 — 제보 판정 임계값 (예시값, 시뮬레이션 테스트로 튜닝 대상)
    tip_discard_threshold: float = 0.2   # p < 0.2 → 파기
    tip_lkp_threshold: float = 0.8       # p ≥ 0.8 + 위치·시각 특정 → 층2 트리거

    # Phase 3 — 층2(Phase 2 재실행) 트리거
    layer2_periodic_minutes: int = 45    # 주기 재실행 (Koester 반경 확장 대응, 30~60분)
    kl_divergence_threshold: float = 0.5 # posterior가 baseline에서 이탈했다고 보는 KL 임계

    # 층1 혼합 likelihood 커널
    likelihood_l_max: float = 5.0        # 목격 지점 셀의 L
    likelihood_l_far: float = 0.1        # 먼 셀의 L (음의 증거)
    likelihood_sigma_cells: float = 2.0  # 가우시안 감쇠 폭 (H3 grid distance 단위)

    # 알림 발송 — POA 상위 셀 누적 커버리지
    alert_coverage: float = 0.8
    # 알림 셀 수 상한 (타겟팅 가드레일) — 꼬리가 두꺼운 분포에서 80% 커버리지가
    # 수천 셀(사실상 무차별)로 폭주하는 것을 차단. res9 셀 ≈0.105km² 기준
    # 500셀 ≈ 52km². 건강한 케이스(경과 1h)는 80% 도달에 ~159셀이라 안 걸린다.
    # 값은 잠정 — POA×POD 실구현 후 평가곡선(알림수 vs 발견율)으로 튜닝 대상.
    max_alert_cells: int = 500

    # ── Phase 3 제보 신뢰도 p (docs: "제보 신뢰도 p 계산 방식") ─────────
    # p = 가중평균(시공간개연성·사진일치·구체성). 없는 신호는 가중치 재정규화.
    # 초기값은 도메인 판단, 합성 시나리오(진짜 vs 가짜 제보 분리)로 튜닝 대상.
    trust_weight_plausibility: float = 0.40  # 시공간 개연성 (kinematic, 알고리즘)
    trust_weight_photo: float = 0.35         # 사진 일치 (VARCO)
    trust_weight_specificity: float = 0.25   # 구체성 (Mi:dm 챗봇)
    trust_base_p: float = 0.3                # 아무 신호도 없을 때의 사전 신뢰

    # kinematic 상한 — v_max(km/h) × Δt = 도달 가능 반경. 넘으면 지수 감쇠.
    # v_max 는 평균이 아니라 "갈 수 있는 최대"(가능성 판정). 고령자 실측 부족 →
    # 추정치, 발표 시 명시. 이동수단 확인 시 transit 값으로 상향.
    reach_vmax_dementia_kmh: float = 4.5
    reach_vmax_child_kmh: float = 4.0
    reach_vmax_id_kmh: float = 5.0
    reach_vmax_transit_kmh: float = 25.0     # 대중교통 목격 확인 시 (도심 버스·지하철)
    reach_min_dt_hours: float = 0.05         # Δt 하한 — 0 나누기·동시목격 방지


settings = Settings()
