"""Fail-closed authorization for cloud jobs. Never forward arbitrary HTTP requests.

Supabase derives owner_id from auth.uid(); the worker receives it from a
service-role-only claim RPC. Client role/user_id/header values grant no access.
The existing API must remain private: this policy protects the bridge, not a
separately exposed uvicorn process.
"""
from dataclasses import dataclass
import re
import math
from urllib.parse import parse_qsl, urlencode, urlsplit
from uuid import UUID

from fastapi import HTTPException
from app import storage


@dataclass
class Request:
    method: str
    path: str
    body: dict | None


def _own(repo, key: str, owner: str, field: str = "guardian_id"):
    row = repo.get(key)
    if row is None or getattr(row, field, None) != owner:
        raise HTTPException(404, "내 계정의 기록을 찾을 수 없습니다.")
    return row


def authorize(owner: str, method: str, path: str, body) -> Request:
    try:
        UUID(owner)
    except (ValueError, TypeError):
        raise HTTPException(401, "로그인이 필요합니다.")
    # No URL decoding ambiguity, HTTP origins, header forwarding or path traversal.
    parts = urlsplit(path)
    if (parts.scheme or parts.netloc or parts.fragment or not path.startswith("/")
            or "//" in parts.path or "%" in parts.path or ".." in parts.path
            or "\\" in path or len(path) > 2048):
        raise HTTPException(400, "지원하지 않는 요청 주소입니다.")
    if body is not None and not isinstance(body, dict):
        raise HTTPException(400, "JSON 객체가 필요합니다.")
    data = dict(body or {})
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    if len(pairs) != len(dict(pairs)):
        raise HTTPException(400, "중복 쿼리는 허용하지 않습니다.")
    query = dict(pairs)
    # Existing private endpoints did not bound every expensive query argument.
    for name, lower, upper in (("top", 1, 128), ("elapsed_hours", 0.01, 24),
                               ("hours", 1, 72), ("limit", 1, 10)):
        if name in query:
            try:
                value = float(query[name])
            except ValueError:
                raise HTTPException(400, "잘못된 조회 범위입니다.")
            if not math.isfinite(value) or not lower <= value <= upper:
                raise HTTPException(400, "허용된 조회 범위를 벗어났습니다.")
    p = parts.path
    allowed = False
    if p.startswith('/phase3/webpush/'):
        allowed = ((p=='/phase3/webpush/public-key' and method=='GET') or
                   (p=='/phase3/webpush/subscription' and method in ('POST','DELETE')) or
                   (p in ('/phase3/webpush/location','/phase3/webpush/enter','/phase3/webpush/test') and method=='POST'))
        if not allowed or query:raise HTTPException(403,'지원하지 않는 알림 요청입니다.')
        data['owner_id']=owner
        return Request(method,p,data if method!='GET' else None)
    if p in ("/phase0/interviews", "/phase0/interviews/sessions") and method == "POST":
        data["guardian_id"] = owner
        allowed = True
    elif p in ("/phase0/personas", "/phase0/personas/status") and method == "GET":
        query["guardian_id"] = owner
        allowed = True
    elif p == "/phase0/personas" and method == "POST":
        if data.get("session_id"):
            _own(storage.interviews, data["session_id"], owner)
        data["guardian_id"] = owner
        allowed = True
    elif m := re.fullmatch(r"/phase0/interviews/([\w-]+)(/answers)?", p):
        allowed = method == ("POST" if m[2] else "GET")
        if allowed:
            _own(storage.interviews, m[1], owner)
    elif m := re.fullmatch(r"/phase0/personas/([\w-]+)/(preparation|prepare)", p):
        allowed = method == ("GET" if m[2]=="preparation" else "POST")
        if allowed:
            _own(storage.personas, m[1], owner)
            data = {}  # clients cannot choose a contract or inject prepared rules
    elif m := re.fullmatch(r"/phase0/personas/([\w-]+)/(confirm)", p):
        allowed = method == "POST"
        if allowed:
            _own(storage.personas, m[1], owner)
            data = {"owner_id": owner}
    elif m := re.fullmatch(r"/phase0/personas/([\w-]+)", p):
        allowed = method in ("GET", "PATCH", "DELETE")
        if allowed:
            _own(storage.personas, m[1], owner)
            data.pop("guardian_id", None)
            if method == "DELETE":
                data = {"owner_id": owner}
    elif p == "/phase1/cases" and method == "GET":
        query = {"guardian_id": owner}
        allowed = True
    elif m := re.fullmatch(r"/phase1/cases/([\w-]+)/close", p):
        allowed = method == "POST"
        if allowed:
            _own(storage.cases, m[1], owner)
            data = {"owner_id": owner, "reason": data.get("reason")}
    elif m := re.fullmatch(r"/phase1/cases/([\w-]+)", p):
        allowed = method in ("GET", "DELETE")
        if allowed:
            _own(storage.cases, m[1], owner)
            if method == "DELETE":
                data = {"owner_id": owner}
    elif p == "/phase1/reports" and method == "POST":
        if data.get("persona_id"):
            _own(storage.personas, data["persona_id"], owner)
        data["guardian_id"] = owner
        allowed = True
    elif m := re.fullmatch(r"/phase1/cases/([\w-]+)(/persona)?", p):
        allowed = method == ("PATCH" if m[2] else "GET")
        if allowed:
            _own(storage.cases, m[1], owner)
            if m[2]:
                _own(storage.personas, data.get("persona_id", ""), owner)
    elif m := re.fullmatch(r"/phase2/cases/([\w-]+)/predict", p):
        allowed = method == "POST"
        if allowed:
            _own(storage.cases, m[1], owner)
    elif p == "/walk/sessions" and method == "POST":
        data["user_id"] = owner
        allowed = True
    elif p in ("/walk/sessions/active", "/walk/stats") and method == "GET":
        query["user_id"] = owner
        allowed = True
    elif m := re.fullmatch(r"/walk/sessions/([\w-]+)/end", p):
        allowed = method == "POST"
        if allowed:
            _own(storage.walk_sessions, m[1], owner, "user_id")
    elif p in ("/phase0/slots", "/phase3/targeting-policy", "/phase3/alerts", "/phase3/alerts/resolved",
               "/geo/search", "/geo/nearby-walks") and method == "GET":
        allowed = True
    elif p == "/geo/labels" and method == "POST":
        if not isinstance(data.get("points"), list) or len(data["points"]) > 64:
            raise HTTPException(400, "한 번에 최대 64개 위치를 조회할 수 있습니다.")
        allowed = True
    elif m := re.fullmatch(r"/phase3/cases/([\w-]+)/(poa|tips|presence|alerts|guidance)", p):
        action = m[2]
        allowed = method in ({"GET"} if action in ("poa", "guidance") else
                             {"GET", "POST"} if action == "presence" else {"POST"})
        if allowed:
            case = storage.cases.get(m[1])
            if case is None:
                raise HTTPException(404, "사건을 찾을 수 없습니다.")
            from app.test_scope import isolated
            if isolated(case):
                _own(storage.cases, m[1], owner)
            if action == "alerts" or "elapsed_hours" in query:
                _own(storage.cases, m[1], owner)
            if action == "tips":
                data["reporter_user_id"] = owner
            if action == "presence" and method == "POST":
                data["token"] = owner
    if not allowed:
        raise HTTPException(403, "공개 앱에서 지원하지 않는 기능입니다.")
    return Request(method, p + ("?" + urlencode(query) if query else ""),
                   data if method != "GET" else None)
