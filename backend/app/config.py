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

    # Phase 0 축 점수 컴파일 (phase0.axis_scoring) — 골드셋 실험으로 검증된 B×P1 채점.
    # 기본 off: 회의에서 채점 방식 채택 시 켠다. runs = 축당 호출 수(3회 다수결 권장).
    axis_scoring_enabled: bool = False
    axis_scoring_runs: int = 3
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
    # 초기값은 도메인 판단, 합성 시나리오(진짜 vs 가짜 제보 분리)로 튜닝 대상.
    trust_weight_plausibility: float = 0.40  # 시공간 개연성 (kinematic, 알고리즘)
    trust_weight_specificity: float = 0.25   # 구체성 (제보 구조화 LLM, tip_llm)
    trust_base_p: float = 0.3                # 아무 신호도 없을 때의 사전 신뢰

    # kinematic 상한 — v_max(km/h) × Δt = 도달 가능 반경. 넘으면 지수 감쇠.
    # v_max 는 평균이 아니라 "갈 수 있는 최대"(가능성 판정). 고령자 실측 부족 →
    # 추정치, 발표 시 명시. 이동수단 확인 시 transit 값으로 상향.
    reach_vmax_dementia_kmh: float = 4.5
    reach_vmax_id_kmh: float = 5.0
    reach_vmax_transit_kmh: float = 25.0     # 대중교통 목격 확인 시 (도심 버스·지하철)
    reach_min_dt_hours: float = 0.05         # Δt 하한 — 0 나누기·동시목격 방지

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
