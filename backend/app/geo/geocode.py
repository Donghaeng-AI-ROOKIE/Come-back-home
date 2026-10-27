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
    detail: dict | None = None   # 후보 고르기용(분류·주소·집에서 거리) — 좌표화 판정에는 쓰지 않는다
    address: str | None = None   # 집 주소 확인 결과를 보호자에게 표시
    # 실제로 걸린 질의 문자열 — locate_home 이 후보 사다리를 내려가며 채운다.
    # 후보 집합(home_alternatives)은 원문이 아니라 **걸린 그 문자열**로 조회해야
    # 한다: "산남동 101동 502호"는 "산남동"으로 걸리는데 원문으로 다시 찾으면 미탐.
    query: str | None = None


@dataclass
class HomeAlternative:
    """집 주소 답 하나가 가리킬 수 있는 후보 한 곳 — 되묻기 보기의 단위.

    address 매치면 (시/도, 시/군/구) 묶음 하나("충북 청주시 서원구"), poi 매치면
    지점 하나("스타벅스 합정점"). label 은 보호자에게 보이는 이름, address 는
    묶음·지점의 대표 주소다.
    """
    label: str
    address: str
    point: GeoPoint
    precision: str          # address | poi
    source: str = "kakao"


# 후보 집합 조회 페이지 크기 — 카카오 상한. 이만큼 꽉 차면 "그 이상"으로 본다.
KAKAO_PAGE_SIZE = 15
# 이 수까지는 보기로 나열, 넘으면 나열하지 않고 더 구체적으로 말해 달라고 한다
# (채팅에서 15줄 목록은 못 읽는다 — "마포구 스타벅스"가 그렇다).
HOME_ALT_MAX_LIST = 5


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

    def home_alternatives(self, res: GeoResult, text: str) -> list[HomeAlternative] | None:
        """집 주소 답이 가리킬 수 있는 후보들. None = 이 백엔드는 판단 못 함(되묻지 않음).

        기본은 None — 다중 결과를 주는 백엔드(카카오)만 구현한다. Nominatim·gazetteer
        가 None 을 돌려주면 온보딩은 오늘과 똑같이 첫 결과를 쓴다.
        """
        return None


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
# 번지·건물번호 — "35", "856-3", "12번지"
_LOT_NUMBER_RE = re.compile(r"^\d+(?:-\d+)?(?:번지)?$")


def has_lot_number(text: str) -> bool:
    """답에 '도로명·동 + 번지'가 있나 — "하남시 하남대로 856 하남더샵센트럴뷰"처럼 뒤에 건물명이
    붙어도 번지가 있으면 **한 곳을 가리키는 주소**다. 집 주소 되묻기가 이걸 상호로 보고
    "'856 하남더샵센트럴뷰'이(가) 여러 곳이에요"라고 묻던 실측(2026-10-27)."""
    toks = str(text or "").split()
    return any(_LOT_NUMBER_RE.match(toks[i]) is not None
               and toks[i - 1].endswith(_ADMIN_SUFFIX + ("로", "길"))
               for i in range(1, len(toks)))


def _looks_like_region(query: str) -> bool:
    """'면목동', '성북구 정릉동'처럼 마지막 토큰이 행정구역 접미사로 끝나는가.

    True  → 주소검색 먼저(동 좌표). '면목동'을 키워드로 넣으면 엉뚱한 랜드마크가 걸림.
    False → 키워드검색 먼저(상호/건물 POI). '면목동 방앗간', '서울숲' 등.
    """
    toks = query.split()
    if not toks:
        return False
    if toks[-1].endswith(_ADMIN_SUFFIX):
        return True
    # "마포구 백범로 35", "면목동 12", "하남대로 856-3" — 번지·건물번호로 끝나는 주소.
    # 마지막 토큰만 보면 숫자라 키워드검색이 먼저 돌아 그 건물 안 POI(서강대학교,
    # "12스톤즈")가 잡히고, 집 주소 되묻기가 그걸 '여러 지점'으로 오인했다(실측 2026-10-27).
    return (len(toks) >= 2 and _LOT_NUMBER_RE.match(toks[-1]) is not None
            and toks[-2].endswith(_ADMIN_SUFFIX + ("로", "길")))


# 지역 표기 토큰 — 한글 2자 이상 + (숫자) + 행정구역/도로 접미사 (+ 번지 숫자).
# 접미사 앞을 2자 이상으로 못 박는 이유: "잠시·우리·바로·친구·운동"처럼 흔한 낱말이
# 한 글자 + 접미사 꼴이라 단순 endswith 로는 전부 지역으로 오인된다(실측: "우리집"→
# 리, "잠시 머무는 곳"→시). 한글로 시작하게 해 아파트 "101동" 도 걸러낸다.
_REGION_TOKEN_RE = re.compile(r"^[가-힣]{2,}[0-9]*(?:시|도|구|군|동|읍|면|리|로|길)[0-9]*$")
# 한 글자 + 구 인데 실제 자치구인 것들("대전 중구") — 위 규칙의 유일한 예외.
_SHORT_DISTRICTS = frozenset({"중구", "동구", "서구", "남구", "북구"})
# 토큰 꼬리 조사 — "정릉동이요"를 "정릉동"으로. '로/으로'는 도로명 접미사와 겹쳐 뺀다.
_TOKEN_PARTICLE_RE = re.compile(r"(?:이에요|예요|이요|입니다|에서|에|요|이|가|은|는)$")


def region_tokens(text: str) -> list[str]:
    """답에 든 지역 표기 토큰들(조사 제거) — "마포구 합정동 스타벅스" → ["마포구", "합정동"].

    has_region_token 의 목록판. 후보 집합을 "답이 말한 지역 안"으로 좁힐 때 쓴다.
    """
    out: list[str] = []
    for tok in str(text or "").split():
        for cand in (tok, _TOKEN_PARTICLE_RE.sub("", tok)):
            if cand in _SHORT_DISTRICTS or _REGION_TOKEN_RE.match(cand):
                out.append(cand)
                break
    return out


def has_region_token(text: str) -> bool:
    """답 어딘가에 지역 표기(시·구·동·도로명)가 있나 — "하남시 더샵센트럴뷰"처럼 앞에 와도 잡는다.

    _looks_like_region 은 검색 순서용(마지막 토큰만)이고, 이건 답에 지역 표기가
    **있기는 한지**를 묻는다. 상호만 적은 답("우리집")은 같은 이름이 전국에 흔해
    좌표를 믿을 수 없으므로 온보딩 집 주소 검증이 이걸로 가른다.
    """
    return bool(region_tokens(text))


# 시/도 정식 명칭 → 카카오 address_name 의 약칭. 보호자는 "충청북도"라 말하고
# 카카오는 "충북"이라 적는다 — 부분 문자열 대조가 이 차이를 넘게 한다.
_SIDO_ALIASES = {
    "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천",
    "광주광역시": "광주", "대전광역시": "대전", "울산광역시": "울산", "세종특별자치시": "세종",
    "경기도": "경기", "강원도": "강원", "강원특별자치도": "강원",
    "충청북도": "충북", "충청남도": "충남", "전라북도": "전북", "전북특별자치도": "전북",
    "전라남도": "전남", "경상북도": "경북", "경상남도": "경남",
    "제주도": "제주", "제주특별자치도": "제주",
}
# 동 이름 뒤 행정동 번호 — 보호자는 "정릉2동"(행정동)이라 말하고 카카오 주소는
# "정릉동"(법정동)으로 적는다.
_DONG_DIGITS_RE = re.compile(r"\d+(?=동$)")
_COARSE_SUFFIX = ("동", "읍", "면", "리", "로", "길")


def _token_variants(tok: str) -> set[str]:
    """주소 문자열과 대조할 때 같은 곳으로 봐야 하는 표기들."""
    out = {tok}
    if tok in _SIDO_ALIASES:
        out.add(_SIDO_ALIASES[tok])
    # "서울시"→"서울", "경기도"→"경기" — 광역 이름은 접미사 없이 적힌다
    if len(tok) >= 3 and tok[-1] in ("시", "도"):
        out.add(tok[:-1])
    out.add(_DONG_DIGITS_RE.sub("", tok))
    return {v for v in out if len(v) >= 2}


def token_in_text(tok: str, text: str) -> bool:
    """지역 토큰이 주소·보기 문자열에 있나 — 약칭·행정동 번호 차이를 넘어 대조한다."""
    return any(v in text for v in _token_variants(tok))


def _is_coarse_region(tok: str) -> bool:
    """시/도·시/군/구 단위인가 — 동·도로명이 아닌 것."""
    return not tok.endswith(_COARSE_SUFFIX)


class KakaoGeocoder(_BaseGeocoder):
    """카카오 Local API — 입력 종류에 따라 검색 순서를 바꾼다.

    - 순수 지역명("면목동", "성북구 정릉동") → 주소검색 먼저 → 동/주소 좌표(precision=address).
    - 상호·장소명("면목동 방앗간", "서울숲")   → 키워드검색 먼저 → 건물 POI(precision=poi).
    각각 실패하면 다른 방식으로 폴백. REST 키 필요.
    """

    source = "kakao"
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
        # 앵커(집)가 있으면 반경 안에서만 찾는다 — "은행 앞" 같은 일반명사가 전국 아무
        # 곳에나 걸리는 것을 API 단에서 차단(radius 상한 20,000m). 정렬은 정확도순이다.
        # 거리순이면 이름이 겹치는 가장 가까운 가게가 첫 결과가 된다 — 2026-09-26 실측
        # (집: 고양시 대화동): '킨텍스'→위피커피, '일산호수공원'→일산들밥, '대화동
        # 노인복지관'→키위 방문요양센터. 정확도순은 셋 다 그 장소 자체를 찾았다.
        extra = ({"x": anchor.lng, "y": anchor.lat,
                  "radius": int(ANCHOR_MAX_KM * 1000), "sort": "accuracy"}
                 if anchor else None)
        docs = self._get(self.KEYWORD_URL, query, extra)
        if not docs:
            return None
        d = docs[0]
        return GeoResult(GeoPoint(lat=float(d["y"]), lng=float(d["x"])),
                         precision="poi", source="kakao", matched=d.get("place_name"),
                         address=d.get("road_address_name") or d.get("address_name") or None)

    def keyword_candidates(self, query: str, anchor: GeoPoint | None = None, size: int = 5) -> list[GeoResult]:
        """키워드 검색 상위 후보(정확도순). 보호자가 말한 곳인지는 호출자가 고른다(모델 판정).

        첫 결과를 그대로 쓰면 이름 일부만 같은 곳이 걸린다 — 최종 게이트 1회차(2026-09-26):
        '일산시장 앞 오거리'·'쌍용아파트 앞 오거리'가 둘 다 1.8km 떨어진 '오거리공원 화장실'로 찍혔다.
        """
        extra = {"size": size, **({"x": anchor.lng, "y": anchor.lat,
                                   "radius": int(ANCHOR_MAX_KM * 1000), "sort": "accuracy"} if anchor else {})}
        out = []
        for d in self._get(self.KEYWORD_URL, query, extra):
            out.append(GeoResult(GeoPoint(lat=float(d["y"]), lng=float(d["x"])), precision="poi", source="kakao",
                                 matched=d.get("place_name"),
                                 detail={"category": str(d.get("category_name") or "").split(" > ")[-1],
                                         "address": d.get("road_address_name") or d.get("address_name") or "",
                                         "distance_m": int(d["distance"]) if d.get("distance") else None}))
        return out

    def _address(self, query: str, anchor: GeoPoint | None = None) -> GeoResult | None:
        # 주소검색 API 는 x/y 파라미터 미지원 — anchor 는 시그니처 통일용
        docs = self._get(self.ADDRESS_URL, query)
        if not docs:
            return None
        d = docs[0]
        # address_type(REGION·ROAD·REGION_ADDR·ROAD_ADDR)은 이 좌표가 번지인지 도로·지역
        # 대표점인지 알려 준다 — 신고 장소 검색의 정밀도 안내가 쓴다(api/geo._granularity).
        return GeoResult(GeoPoint(lat=float(d["y"]), lng=float(d["x"])),
                         precision="address", source="kakao", matched=d.get("address_name"),
                         address=d.get("address_name"), detail={"address_type": d.get("address_type")})

    def locate(self, query: str, anchor: GeoPoint | None = None, *, region: bool = False) -> GeoResult | None:
        if not query:
            return None
        # 순수 지역명이면 주소→키워드, 상호/장소명이면 키워드→주소. region=True 는 호출자가
        # 동네(지역)를 찾는다고 알려 준 경우 — '파주'처럼 접미사 없는 지역명도 주소 먼저.
        steps = ((self._address, self._keyword) if region or _looks_like_region(query)
                 else (self._keyword, self._address))
        for step in steps:
            res = step(query, anchor)
            if res is not None:
                return res
        return None

    def home_alternatives(self, res: GeoResult, text: str) -> list[HomeAlternative] | None:
        """locate 가 첫 결과만 돌려준 답이 실제로는 몇 곳을 가리키는가.

        주소 매치("산남동")는 주소검색을 다시 넓게 받아 **(시/도, 시/군/구)로 묶는다**.
        면목동은 7건(면목본동·2동·4동…)이 오지만 전부 중랑구라 1묶음 — 원시 건수로
        세면 유일한 동네까지 되묻게 된다. 산남동은 파주/청주 2묶음, 중앙동은 15+.

        POI 매치("마포구 스타벅스")는 키워드검색을 넓게 받아 **답에 적힌 지역 토큰을
        주소에 전부 담은 지점만** 남긴다. 카카오는 구 접두어는 지키지만 동은 퍼지해서
        "마포구 합정동 스타벅스"에 서교동·동교동 지점을 섞어 준다(실측 2026-10-01:
        15건 중 합정동은 2건). 동 토큰까지 대조해야 되묻기가 실제로 좁혀진다.
        빈 결과([])는 "첫 결과가 말한 지역 밖" — 강동구에 없는 상호가 타 구로 걸린
        경우라 통과시키면 안 된다. 동만 적은 답("신촌동 스타벅스")은 행정동/법정동이
        어긋날 수 있어(신촌동↔창천동) 엄격 대조가 0건이면 구 단위로 다시 거르고,
        구 토큰조차 없으면 판단을 포기한다(None — 오늘과 같은 동작).
        """
        query = res.query or text
        if res.precision == "address":
            docs = self._get(self.ADDRESS_URL, query, {"size": KAKAO_PAGE_SIZE})
            if not docs:
                return None                      # 조회 실패 — 판단 불가
            groups: dict[tuple[str, str], HomeAlternative] = {}
            for d in docs:
                a = d.get("address") or d.get("road_address") or {}
                key = (a.get("region_1depth_name") or "", a.get("region_2depth_name") or "")
                if key == ("", "") or key in groups:
                    continue
                groups[key] = HomeAlternative(
                    label=" ".join(k for k in key if k),
                    address=d.get("address_name") or "",
                    point=GeoPoint(lat=float(d["y"]), lng=float(d["x"])),
                    precision="address")
            return list(groups.values())
        if res.precision == "poi":
            docs = self._get(self.KEYWORD_URL, query, {"size": KAKAO_PAGE_SIZE})
            if not docs:
                return None
            toks = region_tokens(text)
            coarse = [t for t in toks if _is_coarse_region(t)]
            for wanted in (toks, coarse):
                if not wanted:
                    return None                  # 대조할 지역 토큰이 없다
                out: list[HomeAlternative] = []
                seen: set[str] = set()
                for d in docs:
                    addr = f"{d.get('address_name') or ''} {d.get('road_address_name') or ''}"
                    if not all(token_in_text(t, addr) for t in wanted):
                        continue
                    name = d.get("place_name") or ""
                    if not name or name in seen:
                        continue
                    seen.add(name)
                    out.append(HomeAlternative(
                        label=name,
                        address=d.get("road_address_name") or d.get("address_name") or "",
                        point=GeoPoint(lat=float(d["y"]), lng=float(d["x"])),
                        precision="poi"))
                if out or wanted is coarse:
                    return out
            return None
        return None


# ── OSM Nominatim ────────────────────────────────────────────────────
class NominatimGeocoder(_BaseGeocoder):
    source = "nominatim"
    URL = "https://nominatim.openstreetmap.org/search"

    def __init__(self, timeout: float = 8.0, country: str = "kr") -> None:
        self.timeout = timeout
        self.country = country

    def locate(self, query: str, anchor: GeoPoint | None = None) -> GeoResult | None:
        results = self.keyword_candidates(query, anchor, size=1)
        return results[0] if results else None

    def keyword_candidates(self, query: str, anchor: GeoPoint | None = None, size: int = 5) -> list[GeoResult]:
        import json
        import math
        import urllib.parse
        import urllib.request

        if not query:
            return []
        q: dict = {"q": query, "format": "json", "limit": max(1, min(size, 10)), "countrycodes": self.country}
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
            return []
        if not rows:
            return []
        return [GeoResult(
            GeoPoint(lat=float(r["lat"]), lng=float(r["lon"])),
            precision="approx", source="nominatim", matched=r.get("display_name"),
            address=r.get("display_name"),
            detail={k: r[k] for k in ("osm_type", "osm_id", "type", "class", "category") if k in r},
        ) for r in rows]


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

    source = "gazetteer"

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

    def keyword_candidates(self, query: str, anchor: GeoPoint | None = None, size: int = 5) -> list[GeoResult]:
        for b in self.backends:
            if hasattr(b, "keyword_candidates"):
                results = b.keyword_candidates(query, anchor, size)
                if results:
                    return results
        return []

    def home_alternatives(self, res: GeoResult, text: str) -> list[HomeAlternative] | None:
        """결과를 낸 백엔드가 판단한다 — 카카오 좌표를 nominatim 후보로 되묻지 않는다."""
        for b in self.backends:
            if getattr(b, "source", None) == res.source:
                return b.home_alternatives(res, text)
        return None

    def locate(self, query: str, anchor: GeoPoint | None = None, *, region: bool = False) -> GeoResult | None:
        for b in self.backends:
            hit = b.locate(query, anchor, region=True) if region and isinstance(b, KakaoGeocoder) \
                else b.locate(query, anchor)
            if hit is not None:
                return hit
        return None


def get_geocoder(use_nominatim: bool = False) -> Geocoder:
    """설정 기반 체인. kakao_rest_key 있으면 카카오 우선 → (nominatim) → gazetteer."""
    from app.config import settings

    from app.geo.named_place_cache import NamedPlaceCache
    cached = NamedPlaceCache(settings.roadnet_cache_dir)
    backends: list[Geocoder] = [cached] if cached.path.is_file() else []
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
    chooser=None,
) -> tuple[list[AttractionPoint], list[dict]]:
    """온보딩 초안 [{"label","area_text"}] → (AttractionPoint[], 미해결[]).

    chooser(모델 판정기)가 있고 지오코더가 후보 목록을 줄 수 있으면, 이름 있는 장소는 검색 후보
    중 보호자가 말한 곳을 chooser 가 고른다(없으면 보호자 말에 그대로 나온 랜드마크로 다시 찾아
    그 옆으로 둔다, precision=approx). 고른 곳이 없으면 동네 좌표, 그것도 없으면 미해결 —
    틀린 곳에 목적지를 두지 않는다. chooser 가 없으면 아래 기존 후보 사다리를 쓴다.

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
        area = clean_area_text(d.get("area_text"))
        if d.get("name_kind") == "generic":
            # 고유한 이름 없이 부른 곳("교회", "예전에 살던 집" — 온보딩 모델 판정)은 라벨로
            # 검색하면 집에서 가장 가까운 아무 교회·'…집' 가게가 걸린다. E2E(2026-09-26):
            # 보호자가 '파주시 아동동'이라고 답한 '교회'가 집 60m 옆 교회로 찍혔다(키워드
            # 검색이 집 기준 거리순). 보호자가 말한 동네의 좌표를 쓰고, 동네를 모르면
            # 좌표를 만들지 않는다 — 틀린 곳에 목적지를 두는 것보다 비워 두는 편이 낫다.
            res = _locate_region(geocoder, area, anchor) if area else None
            far = (res is not None and anchor is not None
                   and h3grid.haversine_km(anchor, res.point) > ANCHOR_MAX_KM)
            if res is None or far:
                reason = (f"집 기준 {ANCHOR_MAX_KM:.0f}km 밖 매칭 — 오검색 의심" if far
                          else "이름 없는 장소 — 동네 미확인" if not area else "동네 좌표화 실패")
                unresolved.append({**d, "reason": reason})
                continue
            points.append(AttractionPoint(
                label=label or area, location=res.point, precision=res.precision,
                place_type=str(d.get("place_type") or ""), evidence=coerce_evidence(d.get("evidence")),
                origin_slot=str(d.get("origin_slot") or "")))
            continue
        if chooser is not None and hasattr(geocoder, "keyword_candidates"):
            res, _ = _choose_place(geocoder, chooser, d, label, area, anchor)
            if res is None:
                unresolved.append({**d, "reason": "검색 후보 중 보호자가 말한 곳 없음"})
                continue
            points.append(AttractionPoint(
                label=d.get("label") or area, location=res.point, precision=res.precision,
                place_type=str(d.get("place_type") or ""), evidence=coerce_evidence(d.get("evidence")),
                origin_slot=str(d.get("origin_slot") or "")))
            continue
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


def _choose_place(geocoder, chooser, d: dict, label: str, area: str, anchor: GeoPoint | None):
    """(GeoResult, 방식) — 방식: picked / landmark / area. 못 고르면 (None, None)."""
    from app.geo import h3grid

    def near(results):
        return [r for r in results if anchor is None or h3grid.haversine_km(anchor, r.point) <= ANCHOR_MAX_KM]

    queries = ([f"{area} {label}"] if label and area and label not in area and area not in label else []) + [label]
    queries += [re.sub(r"\s+", "", q) for q in queries]
    seen = set()
    for q in dict.fromkeys(q for q in queries if q):
        results = near(geocoder.keyword_candidates(q, anchor))
        key = tuple((r.matched, round(r.point.lat, 5), round(r.point.lng, 5)) for r in results)
        if not results or key in seen:
            continue      # 같은 후보 목록을 두 번 묻지 않는다(띄어쓰기 변형)
        seen.add(key)
        idx = chooser.pick(d, results)
        if idx is not None:
            return results[idx], "picked"
    landmark = chooser.landmark(d)
    if landmark:
        results = near(geocoder.keyword_candidates(landmark, anchor))
        idx = chooser.pick(d, results, landmark=landmark) if results else None
        if idx is not None:
            r = results[idx]
            return GeoResult(r.point, "approx", r.source, r.matched, {**(r.detail or {}), "landmark": landmark}), "landmark"
    if area:
        # 동네 좌표는 주소 검색 결과만 받는다 — 지역 검색도 주소가 없으면 키워드 첫 결과로 넘어가는데,
        # 10회차 P02 에서 그 첫 결과가 다시 1.5km 떨어진 '오거리공원 화장실'이었다(area = 장소 이름 그대로).
        r = _locate_region(geocoder, area, anchor)
        if (r is not None and r.precision == "address"
                and (anchor is None or h3grid.haversine_km(anchor, r.point) <= ANCHOR_MAX_KM)):
            return r, "area"
    return None, None


# 장소명 뒤에 붙는 '만난 지점' 표현 — 지오코더가 못 찾는 꼬리표다.
# 앞쪽·뒤쪽·옆쪽·부근·인근·근방은 10/27 운영 제보 "능내초등학교 앞쪽에서 봤어요"가
# 위치 없음이 된 뒤 더했다("능내초등학교 앞쪽" → None, "능내초등학교" → LKP 0.5km).
# '쪽' 하나만 떼지는 않는다 — "○○ 동쪽"처럼 장소 이름의 일부일 수 있다.
_PLACE_SUFFIX_RE = re.compile(
    r"\s*(\d+\s*번\s*출구|출구|입구|정문|후문|앞쪽|뒤쪽|옆쪽|앞|뒤|옆"
    r"|근처|주변|부근|인근|근방|건너편|맞은편)\s*$")


def _locate_region(geocoder, area: str, anchor: GeoPoint | None) -> GeoResult | None:
    """동네(지역) 좌표 — 카카오면 주소 검색을 먼저 쓴다('파주' 키워드 → 근처 낚시점 실측)."""
    if isinstance(geocoder, (KakaoGeocoder, ChainGeocoder)):
        return geocoder.locate(area, anchor, region=True)
    return geocoder.locate(area, anchor)


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
    from dataclasses import replace

    for i, q in enumerate(home_candidates(text)):
        hit = geocoder.locate(q)
        if hit is not None:
            if i > 0:
                print(f"[geo] 집 주소 축약 매칭: {text!r} → {q!r} "
                      f"({hit.source}/{hit.precision})")
            # 복사본에 담는다 — 테스트 스텁이 모듈 상수 GeoResult 를 공유해서 돌려준다
            return replace(hit, query=q)
    return None


def clean_area_text(raw) -> str:
    """area_text 정규화 — 공백만 정리한다.

    LLM 이 '없음'을 빈 값 대신 "언급 없음" 같은 문자열로 채우는 실측(2026-07-21)은
    예전에 자리표시 단어 목록으로 걸렀다. 이제는 온보딩이 지역 표기를 보호자 답과
    대조해(phase0.interview._area_grounded) 답에 없는 값을 비운다 — 단어의 뜻을 코드가
    정하지 않는다.
    """
    return " ".join(str(raw or "").split())


def coerce_evidence(raw) -> AttractionEvidence:
    """LLM 추출값 → enum. 모르는 값·누락은 최약 근거(mention_only)로 — 과대평가 방지."""
    try:
        return AttractionEvidence(raw)
    except ValueError:
        return AttractionEvidence.mention_only
