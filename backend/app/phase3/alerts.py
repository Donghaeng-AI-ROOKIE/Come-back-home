"""Phase 3 — 알림: POA 상위 셀 내 사용자에게 타겟 발송 + D3(3차, 새 지역 한정).

광범위 재난문자 대신 발견 확률이 높은 위치의 사용자에게만 보내
알림 피로도를 낮춘다 (핵심 차별점).
"""

import math
from datetime import datetime, timedelta
import threading

from app.config import settings
from app.geo import h3grid, reverse
from app.phase3 import devices, push
from app.schemas.case import Case
from app.schemas.common import GeoPoint


def _cumulative_top_cells(
    ranked: list[tuple[str, float]],
    target_total: float,
    coverage: float,
    max_cells: int,
) -> list[str]:
    """확률 내림차순 목록에서 target_total 의 coverage 비율에 도달할 때까지
    셀을 누적 선택 (select_alert_cells·select_new_region_cells 공용 로직).

    셀 수 상한(max_cells)은 타겟팅 가드레일: 얇은 꼬리가 수천 셀에 퍼져
    있으면 커버리지 기준만으로는 사실상 무차별 발송이 된다(실측: topdown
    σ 오교정 시 21,950셀, 경과 20h 케이스 3,684셀). 상한에 걸리면 커버리지
    미달이어도 끊는다 — "타겟 알림" 이 서비스 전제이므로.
    """
    selected: list[str] = []
    acc = 0.0
    threshold = coverage * target_total
    for cell, prob in ranked:
        if len(selected) >= max_cells:
            break
        selected.append(cell)
        acc += prob
        if acc >= threshold:
            break
    return selected


def select_alert_cells(
    poa: dict[str, float],
    coverage: float | None = None,
    max_cells: int | None = None,
    *, policy: str | None = None, max_area_km2: float | None = None,
    target_res: int | None = None,
) -> list[str]:
    """설정된 커버리지 또는 실제 발송 면적 상한으로 대상 선택.

    coverage 정책은 누적 확률, area_budget 정책은 확률 밀도로 정렬한다.
    면적 정책은 실제 발송 구역의 상한이며 95% 확률 보장이 아니다.
    """
    # 기본값 대입은 `or` 가 아니라 `is None` — coverage=0.0·max_cells=0 을
    # 명시적으로 넘겨도 falsy 라 기본값으로 치환되던 버그 방지.
    coverage = settings.alert_coverage if coverage is None else coverage
    max_cells = settings.max_alert_cells if max_cells is None else max_cells
    policy = settings.alert_selection_policy if policy is None else policy
    if policy == "area_budget":
        from app.phase3.area_budget import select
        return select(poa, settings.max_alert_area_km2 if max_area_km2 is None else max_area_km2,
                      max_cells, settings.push_target_res if target_res is None else target_res)
    if policy != "coverage":
        raise ValueError('unsupported alert selection policy')
    # 비유한값(NaN/inf) 셀 제외 — 정렬 불안정·acc 오염(NaN 누적 시 커버리지
    # 판정 무력화) 방지. 상류(전략확률 가드레일)에서 막지만 심층 방어.
    ranked = sorted(
        ((c, p) for c, p in poa.items() if math.isfinite(p)),
        key=lambda kv: (-kv[1], kv[0]),
    )
    return _cumulative_top_cells(ranked, target_total=1.0, coverage=coverage, max_cells=max_cells)


def select_new_region_cells(
    current_poa: dict[str, float],
    last_alert_poa: dict[str, float],
    mass_threshold: float | None = None,
    coverage: float | None = None,
    max_cells: int | None = None,
) -> list[str]:
    """D3(3차 알림) 최종판정 — 마지막 알림 시점엔 없던 셀(집합차) 중,
    그 새 지역의 **합산** 질량이 임계를 넘을 때만 그 안에서 상위 커버리지만 발송.

    KL/JS가 아니라 집합차인 이유: 새 지역은 last_alert_poa 에서 질량이
    0인 칸인데 KL(new‖old)은 바로 그 지점에서 무한대로 터진다
    (하필 탐지하려는 지점에서 망가짐). 비교 기준이 "직전 POA"가 아니라
    "마지막 알림 시점 POA"인 이유: 작은 제보가 누적돼 서서히 새 동네로
    이동해도 직전 대비 변화량은 매 스텝 작아 영영 안 걸리기 때문 —
    마지막 알림 대비로 재야 누적 이동을 잡는다.

    질량 임계가 **셀 하나**가 아니라 **새 지역 전체 합**인 이유(실측으로 확인):
    시뮬레이션은 새 LKP 주변 확률을 여러 셀에 걸쳐 퍼뜨리므로 새로 생긴 확률은
    거의 항상 셀 하나가 아니라 수십~수백 개에 나눠 담긴다(실측: 새 셀 149개,
    최대 단일 셀 1.3% — 셀 단위 임계 0.05는 절대 못 넘김. 그런데 149개 합산은
    21% — 명백히 알림 가치가 있는 새 지역). 셀 단위 임계는 D3 가 원래 잡으려는
    바로 그 상황(새 LKP 로 넓게 퍼지는 직후)에서 항상 무반응이 되는 결함이었다.
    유의미하다고 판정된 뒤의 실제 타겟팅은 select_alert_cells 와 같은 커버리지
    +상한 로직(무차별 발송 방지)을 새 지역 부분집합에 그대로 재사용한다.
    """
    mass_threshold = (
        settings.new_region_mass_threshold if mass_threshold is None else mass_threshold
    )
    coverage = settings.alert_coverage if coverage is None else coverage
    max_cells = settings.max_alert_cells if max_cells is None else max_cells

    if settings.alert_selection_policy == "area_budget":
        # A dense literature prior has the same support at successive updates.
        # D3 compares delivered selections, not just positive support keys.
        selected = select_alert_cells(current_poa, coverage, max_cells)
        old_targets = target_parent_cells(select_alert_cells(last_alert_poa, coverage, max_cells))
        from app.geo import h3cover
        fresh = [c for c in selected if h3cover.cover([c],settings.push_target_res)-old_targets]
        return fresh if sum(current_poa[c] for c in fresh) >= mass_threshold else []
    new_cells = set(current_poa) - set(last_alert_poa)
    ranked = sorted(
        ((c, current_poa[c]) for c in new_cells if math.isfinite(current_poa[c])),
        key=lambda kv: kv[1], reverse=True,
    )
    total_new_mass = sum(p for _, p in ranked)
    if total_new_mass < mass_threshold:
        return []
    return _cumulative_top_cells(ranked, target_total=total_new_mass, coverage=coverage, max_cells=max_cells)


def targeting_policy_name():
    return ("selected_area_budget_geographic_cover_v1" if settings.alert_selection_policy == "area_budget"
            else "selected_coverage_geographic_cover_v1")


def targeting_metadata():
    return {"target_res": settings.push_target_res,
            "coverage": settings.alert_coverage if settings.alert_selection_policy == "coverage" else None,
            "max_area_km2": settings.max_alert_area_km2 if settings.alert_selection_policy == "area_budget" else None,
            "targeting_policy": targeting_policy_name(),
            "selection_policy": settings.alert_selection_policy,
            "selection_scope": "poa_and_new_region"}


def select_reflex_cells(lkp: GeoPoint, k: int | None = None) -> list[str]:
    """1차 안전반경 (Reflex Tasking) — POA 없이 IPP 주변 k-ring 선택.

    Koester 원칙: 수색 초반에는 복잡한 확률 분석보다 즉시 확인이 중요.
    신고 접수 직후 Phase 2 예측이 나오기 전의 골든타임을 이 알림이 메운다.
    예측 완료 후에는 select_alert_cells(POA 기반)로 전환.
    """
    k = settings.reflex_kring if k is None else k
    return h3grid.cells_within_k(lkp, k)


def target_parent_cells(cells: list[str], res: int | None = None) -> set[str]:
    """선택된 예측 셀과 지리적으로 겹치는 coarse 셀 전체.

    H3 논리 부모는 지리 경계를 완전히 덮지 않는다. 경계 양쪽 기기도 같은
    선택 구역의 대상이 되도록 교차 면적이 있는 셀을 포함한다. 기기는 여전히
    res7 위치 하나만 전송한다.
    """
    from app.geo.h3cover import cover
    return cover(cells, settings.push_target_res if res is None else res)


def relative_prob_by_parent(
    poa: dict[str, float], res: int | None = None
) -> dict[str, float]:
    """res7 부모 셀 → 그 안의 **최고 상대확률**.

    피로도 예산의 확률 문턱은 프론트 히트맵과 같은 **상대 스케일**(최고 셀 대비)로
    정의돼 있다. POA 원값은 전체 합이 1이라 최고 셀도 실측 0.18 수준이고, 그
    스케일로 문턱을 잡으면 아무에게도 알림이 안 간다. 지도 색과 알림 여부를
    일치시키려면 서버도 같은 환산을 써야 한다.

    부모 안의 값 여러 개를 **최대**로 접는 이유: 기기는 res7 칸 어딘가에 있을 뿐
    정확히 어느 res9 셀인지 모른다. 최대를 쓰면 "그 칸에서 가장 유력한 곳" 기준이
    되어 대상을 넓게 잡는데, 놓친 알림이 성가신 알림보다 비싸므로 이쪽이 맞다.
    """
    res = res or settings.push_target_res
    if not poa:
        return {}
    peak = max(poa.values())
    if peak <= 0:
        return {}
    out: dict[str, float] = {}
    for cell, prob in poa.items():
        # 프론트 client.ts 와 같은 환산식 — 최고 셀이 0.9 가 되도록.
        rel = min(0.95, (prob / peak) * 0.9)
        parent = h3grid.parent_cells([cell], res).pop()
        if rel > out.get(parent, 0.0):
            out[parent] = rel
    return out


def describe_alert(case: Case, now: datetime | None = None) -> dict:
    """살아 있는 사건 하나 → 앱이 받는 경보 표현.

    **푸시 페이로드와 같은 모양이어야 한다.** 앱은 두 경로로 경보를 알게 되는데
    (푸시 도착 / 앱 열 때 조회), 관문 판정은 같은 코드가 한다 — 모양이 갈리면
    "알림으로 온 건 뜨는데 앱을 열면 안 뜬다" 같은 어긋남이 생긴다.

    ## kind 는 예측 유무로 갈린다
    POA 가 아직 없으면 신고 직후 골든타임 구간이라 `reflex`(1차 안전반경),
    있으면 `poa`. `new_region`(D3)은 **발송 시점의 판단**이라 여기서는 안 나온다 —
    "지금 살아 있는 사건"에 새 지역이냐 아니냐는 상태가 아니다.

    ## issued_at 이 관문 억제를 되돌리는 축이다
    "그만 볼래요"는 억제 시각보다 **나중에 발령된** 경보에만 뚫린다
    (utils/alertGate.shouldGate). 그래서 마지막 발송 시각이 있으면 그것을 쓴다 —
    새 알림이 나갔다는 건 새로 알릴 일이 생겼다는 뜻이므로.
    """
    from app import storage  # 순환 임포트 회피 (storage → schemas → 여기)

    now = now or datetime.now()
    if case.current_poa:
        cells = select_alert_cells(case.current_poa)
        kind = "poa"
    else:
        cells = select_reflex_cells(case.lkp)
        kind = "reflex"

    elapsed_h = (now - case.lkp_time).total_seconds() / 3600
    look = case.report.appearance
    persona = storage.personas.get(case.report.persona_id) if case.report.persona_id else None
    return {
        "case_id": case.id,
        "issued_at": case.last_alert_at or case.created_at,
        # 최종 목격 지점의 지역명 — **캐시만 읽는다**(geo/reverse.cached_label).
        # 채우는 일은 신고 접수 때 미리 해 둔다. 이 함수는 시민 앱이 15초마다 부르는
        # 폴링 경로라 여기서 외부 호출을 하면 OSM 이 느린 날 경보가 통째로 늦어진다.
        # 아직 안 채워졌거나 조회에 실패했으면 빈 문자열이고 앱이 "내 주변"으로
        # 물러난다 — 좌표에서 동 이름을 지어내지는 않는다.
        "area": reverse.cached_label(case.lkp),
        "severity": "critical" if elapsed_h <= settings.alert_critical_window_h else "active",
        "kind": kind,
        "target_cells": sorted(target_parent_cells(cells)) if cells else [],
        "target_res": settings.push_target_res,
        "targeting_policy": targeting_policy_name(),
        "summary": look.summary if look and look.summary else "인상착의 정보 없음",
        "matched_person_id": case.report.persona_id,
        # 시민 화면이 띄울 최소 신원 — 🚨 **이름은 보내지 않는다.** 나이·인상착의로
        # 충분하고, 이름까지 뿌리면 목적(발견 제보)을 넘는 제공이 된다.
        # (수색 탭 안내 문구에는 이름이 들어가는데, 그건 노출 범위가 다르다 —
        #  storytelling.ToneParams.name 주석 참고)
        "age": persona.age if persona else None,
        # 빈 칸은 빼고 보낸다 — 보호자가 신발을 안 적으면 앱에 **빈 칩**이 뜬다
        # (실측 08-11: ['', '', '', '노란색 상의…'] 로 3칸이 비어 나왔다).
        "appearance": (
            [x for x in (look.top, look.bottom, look.shoes, look.etc) if x and x.strip()]
            if look else []
        ),
        # 실루엣 아바타용 색 태그(schemas/report.Appearance 주석 참고 — 백엔드는
        # 이미지를 만들지 않고 색 이름만 준다). 사진은 받지도 보내지도 않으므로
        # 앱이 사람 사진을 띄우면 그건 실종자가 아닌 남의 얼굴이다.
        "appearance_colors": {
            "top": look.top_color if look else "unknown",
            "bottom": look.bottom_color if look else "unknown",
            "shoes": look.shoes_color if look else "unknown",
        },
        "lkp": {"lat": case.lkp.lat, "lng": case.lkp.lng},
        "lkp_time": case.lkp_time,
    }


_TITLES = {
    "reflex": "인근에서 실종이 발생했어요",
    "new_region": "새로운 지역에서 목격 가능성이 있어요",
    "poa": "실종자가 이 근처에 계실 수 있어요",
}
_BODIES = {
    "reflex": "주변을 한 번 살펴봐 주세요. {appearance}",
    "new_region": "이 근처에서 실종자가 목격되었을 가능성이 있어요. {appearance}",
    # "예측 구역에 계세요"의 주어는 실종자가 아니라 **수신자**다. 지오펜스를 통과해
    # 받은 알림이므로 이건 단정해도 되는 사실.
    "poa": "AI가 예측한 이동 구역에 계세요. 주변을 살펴봐 주세요. {appearance}",
}


def build_message(kind: str, appearance_summary: str) -> tuple[str, str]:
    """알림 제목·본문. **서버가 완성한다.**

    안드로이드는 데이터만 보내고 앱이 알림을 직접 만들 수 있어서 그렇게 짜기 쉽지만,
    iOS 는 앱 코드가 돌기 전에 OS 가 먼저 알림을 띄운다 — 폰에서 조립하는 구조면
    iOS 에서 빈 알림이 뜬다. 확장 비용을 낮추려고 여기서 채운다.

    문구에 진단명·실명이 들어가지 않는 것에 유의(개인정보 최소성). 인상착의
    요약만 붙이며, 그 요약은 이미 시민 노출 승인 항목이다.
    """
    title = _TITLES.get(kind, _TITLES["poa"])
    body = _BODIES.get(kind, _BODIES["poa"]).format(appearance=appearance_summary)
    return title, body


def eligible_for_alert(device, kind: str, rel_by_parent: dict[str, float],
                       selected_targets: set[str] | None = None) -> bool:
    """Selected coverage is authoritative for event fanout and walking entry.

    A second peak-relative filter erased selected probability mass. Existing delivery and dismissal guards remain separate from probability
    selection; engagement thresholds no longer erase the advertised coverage. With no selection,
    retain the legacy diagnostic threshold for callers outside this path.
    """
    if selected_targets is not None:
        return devices.location_in_targets(devices.location_cell(device), selected_targets)
    return (kind == "reflex" or not rel_by_parent
            or rel_by_parent.get(device.cell_res7 or "", 0.0)
               >= settings.push_prob_threshold[device.engagement.value])


def send_alerts(case_id: str, cells: list[str], appearance_summary: str,
                kind: str = "poa", poa: dict[str, float] | None = None,
                *, only_tokens: set[str] | None = None, delivery_details: bool = False,
                exclude_targets: set[str] | None = None) -> dict:
    """대상 res7 셀 안의 기기에 타겟 알림 발송.

    선택된 예측 셀과 지리적으로 겹치는 res7 대상 구역의 기기만 고른다.
    선택 구역을 참여도별 상대확률 문턱으로 다시 줄이지 않는다. 이 변경으로
    수신 대상은 늘 수 있으며, 실제 전달량은 별도 평가가 필요하다.

    발송 실패는 예외로 올리지 않는다. 신고 접수(reflex_alert_on_intake)에서
    호출되는 경로가 있어, 알림이 실패했다고 접수·예측까지 무너지면 안 된다.

    @param poa 기존 호출 계약과 진단 환산을 위해 유지한 원본 분포.
    """
    from app import storage
    from app.test_scope import isolated
    if isolated(storage.cases.get(case_id)):
        return {"case_id": case_id, "kind": kind, "sent": 0, "failed": 0,
                "sent_tokens": [], "failed_tokens": [], "devices": 0, "in_area": 0,
                "below_threshold": 0, "suppressed": 0, "stub": False,
                "status": "synthetic_isolated", "source_cells": len(cells)}
    title, body = build_message(kind, appearance_summary)
    target_cells = (target_parent_cells(cells) if cells else set()) - (exclude_targets or set())
    # 부모 셀은 3~8개라 페이로드에 그대로 실린다 — 폰이 앱 안 관문 판정에 쓴다.
    payload = {
        "case_id": case_id,
        "kind": kind,   # reflex(1차 안전반경) | poa(예측 기반 타겟) | new_region(3차, 새 지역 한정)
        "target_cells": sorted(target_cells),
        "target_res": settings.push_target_res,
        "targeting_policy": targeting_policy_name(),
        "appearance": appearance_summary,
    }

    candidates = devices.devices_in_cells(target_cells)
    verified_case = storage.cases.get(case_id)
    if (settings.verification_push_persona_id and verified_case is not None
            and verified_case.report.persona_id == settings.verification_push_persona_id):
        import hashlib
        allowed = settings.verification_push_device_sha256
        candidates = [d for d in candidates if len(allowed) == 64
                      and hashlib.sha256(d.token.encode()).hexdigest() == allowed]
    if only_tokens is not None:
        candidates = [d for d in candidates if d.token in only_tokens]
    rel_by_parent = relative_prob_by_parent(poa) if poa else {}

    recipients = []
    below_threshold = 0
    for device in candidates:
        if eligible_for_alert(device, kind, rel_by_parent, target_cells):
            recipients.append(device)
        else:
            below_threshold += 1

    tokens = [d.token for d in recipients]
    result = push.send(tokens, title=title, body=body, data=payload)
    if result["sent"]:
        devices.record_sent(result.get("sent_tokens", tokens))

    details = {"failed_tokens": result.get("failed_tokens", []),
               "sent_tokens": result.get("sent_tokens", [])} if delivery_details else {}
    return {
        **details,
        **payload,
        "source_cells": len(cells),
        "title": title,
        "body": body,
        # 왜 이만큼만 갔는지 되짚을 수 있게 단계별 수를 남긴다.
        "in_area": len(candidates),
        "below_threshold": below_threshold,
        "devices": len(tokens),
        "sent": result["sent"],
        "failed": result["failed"],
        "suppressed": result.get("suppressed",0),
        "stub": result["stub"],
    }


def describe_resolved(case: Case) -> dict:
    """종결된 사건 하나 → 시민 화면의 **상황 종료 카드** 표현.

    ## 왜 따로 만드나
    `describe_alert` 를 재사용하지 않는다. 그 함수는 **찾는 데 필요한 정보**를
    담는다 — 인상착의, 색상 태그, 최종 목격 좌표. 이미 찾은 사람에게는 그중
    어느 것도 필요 없고, 계속 뿌리면 목적을 넘는 제공이 된다. 파기 대기 중인
    개인정보이기도 하다.

    그래서 카드가 그리는 것만 남긴다 — 지역, 나이, 종결 시각. 이름은 여기서도
    보내지 않는다(`describe_alert` 와 같은 원칙).

    ## 대상 칸은 왜 여전히 필요한가
    "내 주변에서 있었던 일"만 보여주기 위해서다. 전국의 종결 사건을 다 내려주면
    활성 경보에서 res7 로 최소화해 둔 것을 이 경로가 조용히 무효화한다.
    """
    from app import storage  # 순환 임포트 회피 (describe_alert 와 같은 이유)

    cells = select_alert_cells(case.current_poa) if case.current_poa else select_reflex_cells(case.lkp)
    persona = storage.personas.get(case.report.persona_id) if case.report.persona_id else None
    return {
        "case_id": case.id,
        "area": reverse.cached_label(case.lkp),
        "age": persona.age if persona else None,
        "closed_at": case.closed_at,
        "close_reason": case.close_reason.value if case.close_reason else None,
        "target_cells": sorted(target_parent_cells(cells)) if cells else [],
        "target_res": settings.push_target_res,
        "targeting_policy": targeting_policy_name(),
    }


_notification_lock = threading.RLock()


def notify_prediction(case, *, force=False, now=None, reflex=False) -> dict:
    """Connect successful initial/hourly prediction to the existing POA/D3 policy."""
    from app import storage
    from app.phase3 import triggers
    from app.schemas.case import CaseStatus
    now = now or datetime.now()
    with _notification_lock:
        current = storage.cases.get(case.id)
        if current is None or current.status in (CaseStatus.found, CaseStatus.closed) or (not current.current_poa and not reflex):
            return {"status": "inactive"}
        from app.test_scope import isolated
        if isolated(current):
            return {"status": "synthetic_isolated", "sent": 0}
        pending = current.alert_delivery
        if pending.get("status") == "failed" and pending.get("poa") == (current.current_poa or {}) and not force:
            return {"status": "retry_exhausted"}
        if pending.get("status") == "retry" and pending.get("poa") == (current.current_poa or {}):
            if not force and datetime.fromisoformat(pending["retry_at"]) > now:
                return {"status": "retry_pending"}
            return _deliver_event(current, pending, now)
        kind = "reflex" if reflex else "poa"
        if reflex:
            cells = select_reflex_cells(current.lkp)
        elif current.last_alert_poa and not force:
            if triggers.jensen_shannon_divergence(current.current_poa, current.last_alert_poa) < settings.js_divergence_threshold:
                return {"status": "unchanged"}
            cells = select_new_region_cells(current.current_poa, current.last_alert_poa)
            kind = "new_region"
        else:
            cells = select_alert_cells(current.current_poa)
        if not cells:
            return {"status": "no_target"}
        event = {"id": storage.new_id(), "kind": kind, "cells": cells,
                 "poa": dict(current.current_poa or {}), "attempts": 0, "status": "retry",
                 "retry_at": now.isoformat(), "tokens": None}
        if kind == 'new_region' and settings.alert_selection_policy == 'area_budget':
            # A boundary fine cell can cover both new and previously notified
            # coarse cells. Exclude the old delivery cover, also on retries.
            event['exclude_targets'] = sorted(target_parent_cells(select_alert_cells(current.last_alert_poa)))
        def reserve(latest):
            if latest.status in (CaseStatus.found, CaseStatus.closed):
                return None
            latest.alert_delivery = event
            return latest
        if storage.cases.update_existing(current.id, reserve) is None:
            return {"status": "inactive"}
        return _deliver_event(current, event, now)


def _deliver_event(case, event, now):
    """Persist failures before sending; never recreate a deleted/closed case.

    Vendor acceptance is not delivery to the phone. Successful recipients are
    excluded from retries; the existing web-push receipt also deduplicates them.
    """
    from app import storage
    from app.schemas.case import CaseStatus
    look = case.report.appearance
    try:
        result = send_alerts(case.id, event["cells"], look.summary if look else "인상착의 정보 없음",
                             kind=event["kind"], poa=event["poa"] if event["kind"] == "poa" else None,
                             only_tokens=set(event["tokens"]) if event["tokens"] is not None else None,
                             delivery_details=True,
                             **({"exclude_targets":set(event["exclude_targets"])} if "exclude_targets" in event else {}))
    except Exception:
        result = {"sent": 0, "failed": 1, "stub": False}
    def complete(latest):
        if (latest.status in (CaseStatus.found, CaseStatus.closed)
                or latest.alert_delivery.get("id") != event["id"]):
            return None
        attempt = event["attempts"] + 1
        failed = result.get("failed", 0) > 0
        latest.alert_delivery = {**event, "attempts": attempt,
            "status": "retry" if failed and attempt < 5 else ("failed" if failed else "complete"),
            "retry_at": (now + timedelta(minutes=min(30, 2 ** attempt))).isoformat(),
            "tokens": result.get("failed_tokens", event["tokens"]),
            "sent": result.get("sent", 0), "failed": result.get("failed", 0)}
        if result.get("sent", 0) > 0 and not result.get("stub", False):
            if event["kind"] != "reflex":
                latest.last_alert_poa = dict(event["poa"])
            latest.last_alert_at = now
        return latest
    storage.cases.update_existing(case.id, complete)
    return {k: v for k, v in result.items() if k not in ("sent_tokens", "failed_tokens")}


def retry_pending_notifications(now=None):
    from app import storage
    now = now or datetime.now()
    for case in storage.cases.list():
        if case.alert_delivery.get("status") == "retry":
            notify_prediction(case, now=now, reflex=case.alert_delivery.get("kind") == "reflex")
