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

    # Phase 2 — Monte Carlo
    mc_num_walkers: int = 500

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


settings = Settings()
