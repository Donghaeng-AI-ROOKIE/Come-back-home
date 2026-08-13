"""지오코딩 — 장소 텍스트(동/랜드마크/상호) → 좌표(GeoPoint) + 정밀도.

Phase 0 온보딩 끌림점(area_text: "면목동 방앗간", "성북구 정릉동" 등)을 Phase 2
시뮬레이션 좌표로 바꾼다. draft → Persona.attraction_points 확정의 끊긴 고리.

정밀도(precision)를 함께 반환 — SAR에서 거친 앵커는 반경 넓게, 정밀 POI는 좁게:
  poi(건물·상호) > address(도로명·지번) > dong(동 중심) > approx(근사)

백엔드 교체형(정밀→거침 순 체인):
- KakaoGeocoder:    카카오 Local — 키워드 장소검색(상호까지 건물 좌표) + 주소검색. ★가장 정밀
- NominatimGeocoder: OSM(네트워크, 키 불필요). 카카오 밖 보강.
- GazetteerGeocoder: 오프라인 사전(결정적·키리스). 최후 폴백·테스트용.
config.kakao_rest_key 있으면 카카오 우선.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from app.schemas.common import GeoPoint
from app.schemas.persona import AttractionEvidence, AttractionPoint


@dataclass
class GeoResult:
    point: GeoPoint
    precision: str          # poi | address | dong | approx
    source: str             # kakao | nominatim | gazetteer
    matched: str | None = None   # 실제 매칭된 장소/주소명


class Geocoder(Protocol):
    def locate(self, query: str, anchor: GeoPoint | None = None) -> GeoResult | None: ...
    def geocode(self, query: str) -> GeoPoint | None: ...


# 앵커(집) 기준 끌림점 탐색 반경 상한 (km). 카카오 radius 파라미터 상한(20,000m)과 정합.
# 라이브 인터뷰 실측 버그의 방어선: "은행 앞"→과천 21km, "산책로"→경북 188km 전국 오검색.
ANCHOR_MAX_KM = 20.0


class _BaseGeocoder:
    """geocode() 는 locate() 의 좌표만 뽑아주는 편의 래퍼."""

    def locate(self, query: str, anchor: GeoPoint | None = None) -> GeoResult | None:  # pragma: no cover - 추상
        raise NotImplementedError

    def geocode(self, query: str) -> GeoPoint | None:
        r = self.locate(query)
        return r.point if r else None


# ── 카카오 Local (가장 정밀) ─────────────────────────────────────────
# 이미 알린 인증 실패 상태코드 — 같은 설정 오류를 호출마다 찍지 않기 위해서.
# 끌림점이 여러 개면 한 번의 등록에도 조회가 수십 번 일어난다.
_KAKAO_DENIED_WARNED: set[int] = set()


def _warn_kakao_denied(err) -> None:
    """카카오가 **거부**한 경우만 크게 남긴다 (401 키 문제 · 403 서비스 미활성).

    이 실패는 재시도로 낫지 않는 설정 문제인데, 조용히 미탐으로 넘기면 체인의
    다음 백엔드(nominatim)가 받아 준다. 그러면 앱은 멀쩡히 돌아가고 좌표 품질만
    나빠져서, 키를 넣은 사람은 아무 신호도 받지 못한다 — 실제로 카카오맵 서비스가
    꺼진 채 403 이 나고 있었는데 로그가 없어 한참 뒤 수동 호출로야 찾았다(08-12).
    "키를 넣었는데 왜 그대로지"를 다시 겪지 않도록 이유를 화면에 띄운다.

    응답 본문에 카카오가 앱 이름과 미활성 서비스명을 담아 주므로 그대로 싣는다
    (키는 요청 헤더에만 있고 본문에 없다 — 로그로 새지 않는다).
    """
    code = getattr(err, "code", 0)
    if code not in (401, 403) or code in _KAKAO_DENIED_WARNED:
        return
    _KAKAO_DENIED_WARNED.add(code)
    try:
        detail = err.read().decode("utf-8")[:200]
    except Exception:  # noqa: BLE001 — 본문을 못 읽어도 상태코드만으로 충분히 유용
        detail = ""
    print(f"[geo] 카카오 지오코딩 거부(HTTP {code}) — 이후 nominatim/gazetteer 로 "
          f"폴백합니다. KAKAO_REST_KEY 와 카카오맵 서비스 활성화를 확인하세요. {detail}")

# 행정구역 접미사 — 마지막 토큰이 이걸로 끝나면 '순수 지역명'으로 보고 주소검색 먼저.
_ADMIN_SUFFIX = ("특별시", "광역시", "시", "도", "구", "군", "동", "읍", "면", "리")


def _looks_like_region(query: str) -> bool:
    """'면목동', '성북구 정릉동'처럼 마지막 토큰이 행정구역 접미사로 끝나는가.

    True  → 주소검색 먼저(동 좌표). '면목동'을 키워드로 넣으면 엉뚱한 랜드마크가 걸림.
    False → 키워드검색 먼저(상호/건물 POI). '면목동 방앗간', '서울숲' 등.
    """
    toks = query.split()
    return bool(toks) and toks[-1].endswith(_ADMIN_SUFFIX)


class KakaoGeocoder(_BaseGeocoder):
    """카카오 Local API — 입력 종류에 따라 검색 순서를 바꾼다.

    - 순수 지역명("면목동", "성북구 정릉동") → 주소검색 먼저 → 동/주소 좌표(precision=address).
    - 상호·장소명("면목동 방앗간", "서울숲")   → 키워드검색 먼저 → 건물 POI(precision=poi).
    각각 실패하면 다른 방식으로 폴백. REST 키 필요.
    """

    KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
    ADDRESS_URL = "https://dapi.kakao.com/v2/local/search/address.json"

    def __init__(self, rest_key: str, timeout: float = 8.0) -> None:
        self.rest_key = rest_key
        self.timeout = timeout

    def _get(self, url: str, query: str, extra: dict | None = None) -> list[dict]:
        import json
        import urllib.error
        import urllib.parse
        import urllib.request

        params = {"query": query, "size": 1, **(extra or {})}
        full = f"{url}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(full, headers={"Authorization": f"KakaoAK {self.rest_key}"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8")).get("documents", [])
        except urllib.error.HTTPError as e:
            _warn_kakao_denied(e)
            return []
        except Exception:  # noqa: BLE001 — 네트워크 장애는 조용히 미탐(폴백이 받는다)
            return []

    def _keyword(self, query: str, anchor: GeoPoint | None = None) -> GeoResult | None:
        # 앵커(집)가 있으면 반경 내 근접순 검색 — "은행 앞" 같은 일반명사가
        # 전국 아무 곳에나 걸리는 것을 API 단에서 차단 (radius 상한 20,000m).
        extra = ({"x": anchor.lng, "y": anchor.lat,
                  "radius": int(ANCHOR_MAX_KM * 1000), "sort": "distance"}
                 if anchor else None)
        docs = self._get(self.KEYWORD_URL, query, extra)
        if not docs:
            return None
        d = docs[0]
        return GeoResult(GeoPoint(lat=float(d["y"]), lng=float(d["x"])),
                         precision="poi", source="kakao", matched=d.get("place_name"))

    def _address(self, query: str, anchor: GeoPoint | None = None) -> GeoResult | None:
        # 주소검색 API 는 x/y 파라미터 미지원 — anchor 는 시그니처 통일용
        docs = self._get(self.ADDRESS_URL, query)
        if not docs:
            return None
        d = docs[0]
        return GeoResult(GeoPoint(lat=float(d["y"]), lng=float(d["x"])),
                         precision="address", source="kakao", matched=d.get("address_name"))

    def locate(self, query: str, anchor: GeoPoint | None = None) -> GeoResult | None:
        if not query:
            return None
        # 순수 지역명이면 주소→키워드, 상호/장소명이면 키워드→주소
        steps = (self._address, self._keyword) if _looks_like_region(query) else (self._keyword, self._address)
        for step in steps:
            res = step(query, anchor)
            if res is not None:
                return res
        return None


# ── OSM Nominatim ────────────────────────────────────────────────────
class NominatimGeocoder(_BaseGeocoder):
    URL = "https://nominatim.openstreetmap.org/search"

    def __init__(self, timeout: float = 8.0, country: str = "kr") -> None:
        self.timeout = timeout
        self.country = country

    def locate(self, query: str, anchor: GeoPoint | None = None) -> GeoResult | None:
        import json
        import math
        import urllib.parse
        import urllib.request

        if not query:
            return None
        q: dict = {"q": query, "format": "json", "limit": 1, "countrycodes": self.country}
        if anchor is not None:
            # 앵커 기준 ~ANCHOR_MAX_KM 박스로 제한 (viewbox=left,top,right,bottom + bounded)
            dlat = ANCHOR_MAX_KM / 111.32
            dlng = ANCHOR_MAX_KM / (111.32 * math.cos(math.radians(anchor.lat)))
            q["viewbox"] = f"{anchor.lng - dlng},{anchor.lat + dlat},{anchor.lng + dlng},{anchor.lat - dlat}"
            q["bounded"] = 1
        params = urllib.parse.urlencode(q)
        req = urllib.request.Request(
            f"{self.URL}?{params}",
            headers={"User-Agent": "come-back-home/0.1 (SAR onboarding)"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                rows = json.loads(resp.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            return None
        if not rows:
            return None
        r = rows[0]
        return GeoResult(
            GeoPoint(lat=float(r["lat"]), lng=float(r["lon"])),
            precision="approx", source="nominatim", matched=r.get("display_name"),
        )


# ── 오프라인 gazetteer (최후 폴백) ──────────────────────────────────
_GAZETTEER: dict[str, GeoPoint] = {
    "정릉동": GeoPoint(lat=37.6076, lng=127.0133),
    "면목동": GeoPoint(lat=37.5872, lng=127.0873),
    "화곡동": GeoPoint(lat=37.5417, lng=126.8407),
    "안양천": GeoPoint(lat=37.5290, lng=126.8760),
    "정릉초등학교": GeoPoint(lat=37.6087, lng=127.0155),
    "성북구": GeoPoint(lat=37.5894, lng=127.0167),
    "중랑구": GeoPoint(lat=37.6063, lng=127.0925),
    "강서구": GeoPoint(lat=37.5509, lng=126.8495),
    "종로구": GeoPoint(lat=37.5730, lng=126.9794),
    "강남구": GeoPoint(lat=37.5172, lng=127.0473),
    "노원구": GeoPoint(lat=37.6542, lng=127.0568),
    "은평구": GeoPoint(lat=37.6027, lng=126.9291),
}


def _normalize(text: str) -> str:
    return re.sub(r"[\s()]+", "", text)


class GazetteerGeocoder(_BaseGeocoder):
    """오프라인 사전 매칭 — 긴 키(동)를 먼저 시도해 구보다 동을 우선."""

    def __init__(self, table: dict[str, GeoPoint] | None = None) -> None:
        self.table = table or _GAZETTEER
        self._keys = sorted(self.table, key=len, reverse=True)

    def locate(self, query: str, anchor: GeoPoint | None = None) -> GeoResult | None:
        if not query:
            return None
        q = _normalize(query)
        for key in self._keys:
            if _normalize(key) in q:
                return GeoResult(self.table[key], precision="dong", source="gazetteer", matched=key)
        return None


# ── 체인 ─────────────────────────────────────────────────────────────
class ChainGeocoder(_BaseGeocoder):
    """여러 백엔드를 순서대로 시도, 첫 성공 반환 (정밀→거침 순 권장)."""

    def __init__(self, *backends: Geocoder) -> None:
        self.backends = backends

    def locate(self, query: str, anchor: GeoPoint | None = None) -> GeoResult | None:
        for b in self.backends:
            hit = b.locate(query, anchor)
            if hit is not None:
                return hit
        return None


def get_geocoder(use_nominatim: bool = False) -> Geocoder:
    """설정 기반 체인. kakao_rest_key 있으면 카카오 우선 → (nominatim) → gazetteer."""
    from app.config import settings

    backends: list[Geocoder] = []
    if getattr(settings, "kakao_rest_key", ""):
        backends.append(KakaoGeocoder(settings.kakao_rest_key))
    if use_nominatim:
        backends.append(NominatimGeocoder())
    backends.append(GazetteerGeocoder())
    return backends[0] if len(backends) == 1 else ChainGeocoder(*backends)


# ── draft 끌림점 → AttractionPoint ──────────────────────────────────
def to_attraction_points(
    drafts: list[dict],
    geocoder: Geocoder | None = None,
    *,
    anchor: GeoPoint | None = None,
) -> tuple[list[AttractionPoint], list[dict]]:
    """온보딩 초안 [{"label","area_text"}] → (AttractionPoint[], 미해결[]).

    지오코딩되면 좌표·정밀도(precision) 담아 AttractionPoint 생성, 안 되면 미해결.
    anchor(집 좌표)가 있으면: (1) 백엔드에 근접 검색 힌트로 전달하고,
    (2) 결과가 anchor 에서 ANCHOR_MAX_KM 를 벗어나면 채택하지 않고 미해결 처리 —
    백엔드가 앵커를 무시하는 경우(nominatim 미탐 폴백 등)까지 막는 최종 방어선.
    실측 버그: "은행 앞"→과천 21km, "산책로"→경북 188km (전국 키워드 오검색).

    place_type/evidence 태그는 좌표화 과정에서 증발하지 않게 그대로 통과시킨다
    (근거 분류는 추출 단계에서만 가능 — 여기서 소실되면 복원 불가). weight 는
    균등이 아니라 evidence 계수(schemas.persona.EVIDENCE_PRIOR_WEIGHTS)로 시작한다
    — "과거 실제 발견지"와 "지나가듯 언급"이 같은 무게로 출발하면 안 되기 때문.
    이 값은 뒤에서 EXAONE 등급과 곱셈 병합된다(phase2.guardrail).
    """
    from app.geo import h3grid

    geocoder = geocoder or get_geocoder()
    points: list[AttractionPoint] = []
    unresolved: list[dict] = []
    for d in drafts:
        label = str(d.get("label") or "").strip()
        # 구버전 세션·직접 호출로 들어온 "언급 없음" 류도 여기서 한 번 더 막는다
        # (인터뷰 단계에서 이미 정규화되지만, 이 함수가 마지막 관문이다).
        area = clean_area_text(d.get("area_text"))
        # 후보 쿼리는 구체 장소(라벨) 우선. area_text 를 먼저 쓰던 구버전은 라벨
        # "대흥역"이 area "대흥동"의 동 중심 좌표로 찍히는 라벨-좌표 불일치를 냈다
        # (라이브 실측 2026-07-17). "지역+라벨" 결합 → 라벨 → 지역 순으로 시도하고,
        # 앵커 반경 밖 매칭은 다음 후보로 넘어간다.
        candidates: list[str] = []
        if label and area and label not in area and area not in label:
            candidates.append(f"{area} {label}")
        candidates += [label, area]
        # 공백 제거 변형도 시도 — Mi:dm 이 "망원 시장"처럼 띄어 추출하면 nominatim
        # 이 못 찾아 조용히 탈락하던 실측(2026-07-17 8차). 카카오는 양쪽 다 잘 찾지만
        # 폴백 백엔드는 표기에 민감하다.
        candidates += [re.sub(r"\s+", "", q) for q in candidates]
        # 위치 접미어를 뗀 핵심 지명도 **마지막 후보**로 — 보호자는 "대흥역 2번 출구",
        # "○○아파트 앞"처럼 만난 지점을 그대로 말하는데 지오코더는 그 표기를 못 찾는다
        # (라이브 실측 2026-07-21: '대흥역 2번 출구' → None, '대흥역' → 성공).
        # 정확한 표기를 먼저 다 시도한 뒤에만 쓰므로 정밀도를 깎지 않는다.
        candidates += [base_place_name(q) for q in (label, area)]
        candidates = list(dict.fromkeys(q for q in candidates if q))

        res = None
        rejected_far = False
        for q in candidates:
            r = geocoder.locate(q, anchor)
            if r is None:
                continue
            if anchor is not None and h3grid.haversine_km(anchor, r.point) > ANCHOR_MAX_KM:
                rejected_far = True
                continue
            res = r
            break
        if res is None:
            extra = ({"reason": f"집 기준 {ANCHOR_MAX_KM:.0f}km 밖 매칭 — 오검색 의심"}
                     if rejected_far else {})
            unresolved.append({**d, **extra})
            continue
        points.append(AttractionPoint(
            # weight 는 명시하지 않는다 — AttractionPoint 검증자가 evidence 계수로 채운다.
            label=d.get("label") or area,
            location=res.point,
            precision=res.precision,
            place_type=str(d.get("place_type") or ""),
            evidence=coerce_evidence(d.get("evidence")),
            origin_slot=str(d.get("origin_slot") or ""),
        ))
    return points, unresolved


# LLM 이 '없음'을 빈 값이 아니라 문자열로 채우는 실측(2026-07-21 라이브: area_text
# "언급 없음") — 그대로 두면 (1) 이 문자열이 지오코딩 질의로 나가 실패하고,
# (2) truthy 라서 나중에 들어온 진짜 지역 표기가 병합·정정에서 막힌다.
_PLACEHOLDER_AREA_RE = re.compile(
    r"^(언급\s*없음|없음|미상|불명|모름|모르겠\S*|알\s*수\s*없음|해당\s*없음|"
    r"n\s*/\s*a|none|null|unknown|-+)$", re.IGNORECASE)


# 장소명 뒤에 붙는 '만난 지점' 표현 — 지오코더가 못 찾는 꼬리표다.
_PLACE_SUFFIX_RE = re.compile(
    r"\s*(\d+\s*번\s*출구|출구|입구|정문|후문|앞|뒤|옆|근처|주변|건너편|맞은편)\s*$")


def base_place_name(query: str) -> str:
    """'대흥역 2번 출구' → '대흥역'. 접미어가 겹쳐 붙어도("○○역 앞 근처") 다 뗀다."""
    cur = str(query or "").strip()
    while True:
        stripped = _PLACE_SUFFIX_RE.sub("", cur).strip()
        if stripped == cur or not stripped:
            return cur
        cur = stripped


def home_candidates(text: str) -> list[str]:
    """집 주소 조회 후보를 정밀 → 거침 순으로 만든다.

    보호자는 "하남시 하남대로 856 하남더샵센트럴뷰"처럼 **건물 이름까지** 적는다.
    지오코더는 그 조합을 못 찾는다 — 실측(08-12) 결과가 정확히 이렇다:

        '하남시 하남대로 856 하남더샵센트럴뷰' → None
        '하남시 하남대로 856'                  → 37.5440, 127.2033
        '하남시'                               → 37.5393, 127.2149

    그런데 home 은 실패하면 ValueError 로 **등록 자체가 막힌다**. 보호자는 주소를
    정확히 적었는데 앱이 계속 되묻고, 몇 번을 다시 입력해도 같은 결과가 된다
    (라이브 실측 08-12). 끌림점(to_attraction_points)은 이미 이런 후보 사다리를
    갖고 있었는데 home 만 맨 문자열 한 번으로 끝내고 있었다 — 하필 실패 비용이
    가장 큰 쪽에 없었다.

    사다리를 내려갈수록 좌표가 거칠어지므로(도로명 → 시 중심) 순서가 중요하다.
    정밀한 후보를 **전부** 시도한 뒤에만 거친 것으로 내려간다. 그래도 아무것도
    안 걸리면 호출부가 기존대로 ValueError 를 낸다 — 못 찾은 걸 찾은 척하지 않는다.
    """
    raw = " ".join(str(text or "").split())
    if not raw:
        return []
    # "정릉2동 주민센터 근처"처럼 위치 수식어가 붙으면 원문 검색이 행정구역
    # 중심으로만 성공할 수 있다. 접미어를 제거한 POI 후보를 먼저 시도해야
    # 뒤의 거친 성공이 더 정확한 후보를 가로막지 않는다.
    base = base_place_name(raw)
    out = [base, base.replace(" ", ""), raw, raw.replace(" ", "")]
    tokens = raw.split(" ")
    # 뒤에서부터 한 토큰씩 떼며 재시도 — 건물명·동·호수가 먼저 떨어진다.
    for cut in range(len(tokens) - 1, 1, -1):
        out.append(" ".join(tokens[:cut]))
    # 마지막 보루: 행정구역으로 보이는 토큰만 남긴다("…시 …구 …동").
    admin = [t for t in tokens if t.endswith(_ADMIN_SUFFIX)]
    if admin:
        out.append(" ".join(admin))
        out.append(admin[0])
    seen: set[str] = set()
    uniq: list[str] = []
    for q in out:
        if q and q not in seen:
            seen.add(q)
            uniq.append(q)
    return uniq


def locate_home(geocoder: Geocoder, text: str) -> GeoResult | None:
    """집 주소 좌표화 — home_candidates 를 순서대로 시도, 첫 성공 반환.

    어느 후보로 걸렸는지 로그로 남긴다. 원본과 다른 문자열로 찍혔다는 사실이
    좌표 정밀도를 읽는 단서이고, 조용히 거칠어지면 나중에 추적이 불가능하다.
    """
    for i, q in enumerate(home_candidates(text)):
        hit = geocoder.locate(q)
        if hit is not None:
            if i > 0:
                print(f"[geo] 집 주소 축약 매칭: {text!r} → {q!r} "
                      f"({hit.source}/{hit.precision})")
            return hit
    return None


def clean_area_text(raw) -> str:
    """area_text 정규화 — 플레이스홀더는 빈 문자열로. '지역 미상'과 '미기입'을 같게 만든다."""
    text = str(raw or "").strip()
    return "" if _PLACEHOLDER_AREA_RE.match(text) else text


def coerce_evidence(raw) -> AttractionEvidence:
    """LLM 추출값 → enum. 모르는 값·누락은 최약 근거(mention_only)로 — 과대평가 방지."""
    try:
        return AttractionEvidence(raw)
    except ValueError:
        return AttractionEvidence.mention_only
