"""로그인 — 아이디/비밀번호.

앱의 시작 화면이 역할 버튼 두 개였다. 누가 켜도 같은 `demo-citizen` 으로 들어가서
남의 산책 기록이 보였고, 아이디를 칠 자리가 아예 없었다. 여기서 계정을 만든다.

## 설계 경계
- 비밀번호는 scrypt + 계정별 salt 로만 저장한다. 원문은 저장·로깅하지 않는다.
- 응답에 해시를 담지 않는다 — 앱이 알 필요가 없다.
- 아이디 존재 여부를 로그인 실패 메시지로 구분하지 않는다(계정 열거 방지).
- 토큰에 만료를 두지 않는다. 현장 수색 중 갑자기 로그아웃되는 쪽이 더 위험하다.
"""

import hashlib
import re
import secrets

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app import storage
from app.schemas.account import Account, Session

router = APIRouter(prefix="/auth", tags=["인증 — 계정"])

# scrypt 파라미터 — 로그인 1회 ≈ 수십 ms. 맥미니 한 대에서 현장 인원이 동시에
# 로그인해도 버티는 선으로 잡았다.
_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}

# 시안이 "이메일 주소"를 받으므로 이메일을 허용한다. 다만 이메일만 강제하지는
# 않는다 — 현장 실험에서 짧은 아이디로 빨리 만들 수 있어야 한다.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")
_ID_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,32}$")


def _valid_login_id(value: str) -> bool:
    return bool(_EMAIL_RE.match(value) or _ID_RE.match(value))
_ROLES = {"citizen", "guardian"}


def _hash(password: str, salt_hex: str) -> str:
    return hashlib.scrypt(
        password.encode("utf-8"), salt=bytes.fromhex(salt_hex), **_SCRYPT
    ).hex()


class CredentialsIn(BaseModel):
    login_id: str
    password: str
    role: str = "citizen"   # 가입에만 쓰인다. 로그인은 저장된 역할을 따른다.


class AuthOut(BaseModel):
    token: str
    user_id: str
    login_id: str
    role: str


def _issue(account: Account) -> AuthOut:
    token = secrets.token_urlsafe(24)
    storage.sessions.save(
        token,
        Session(
            token=token,
            user_id=account.user_id,
            login_id=account.login_id,
            role=account.role,
        ),
    )
    return AuthOut(
        token=token,
        user_id=account.user_id,
        login_id=account.login_id,
        role=account.role,
    )


def _find(login_id: str) -> Account | None:
    for acc in storage.accounts.list():
        if acc.login_id == login_id:
            return acc
    return None


@router.post("/signup", response_model=AuthOut)
def signup(body: CredentialsIn) -> AuthOut:
    """가입 즉시 로그인 상태가 된다 — 현장에서 화면을 두 번 거치게 하지 않는다."""
    login_id = body.login_id.strip().lower()
    if len(login_id) > 64 or not _valid_login_id(login_id):
        raise HTTPException(400, "이메일 주소 형식으로 입력해 주세요.")
    if len(body.password) < 4:
        raise HTTPException(400, "비밀번호는 4자 이상으로 입력해 주세요.")
    if body.role not in _ROLES:
        raise HTTPException(400, "역할이 올바르지 않습니다.")
    if _find(login_id) is not None:
        raise HTTPException(409, "이미 있는 아이디입니다.")

    salt = secrets.token_hex(16)
    account = Account(
        user_id=f"u-{secrets.token_hex(6)}",
        login_id=login_id,
        role=body.role,
        password_hash=_hash(body.password, salt),
        password_salt=salt,
    )
    storage.accounts.save(account.user_id, account)
    return _issue(account)


@router.post("/login", response_model=AuthOut)
def login(body: CredentialsIn) -> AuthOut:
    """실패 사유를 아이디/비밀번호로 나누지 않는다 — 계정 열거를 막는다."""
    login_id = body.login_id.strip().lower()
    account = _find(login_id)
    if account is None or _hash(body.password, account.password_salt) != account.password_hash:
        raise HTTPException(401, "아이디 또는 비밀번호가 올바르지 않습니다.")
    return _issue(account)


@router.get("/me", response_model=AuthOut)
def me(authorization: str = Header(default="")) -> AuthOut:
    """토큰 확인 — 앱이 재시작 후 저장해 둔 토큰이 아직 유효한지 묻는다."""
    token = authorization.removeprefix("Bearer ").strip()
    session = storage.sessions.get(token)
    if session is None:
        raise HTTPException(401, "다시 로그인해 주세요.")
    return AuthOut(
        token=session.token,
        user_id=session.user_id,
        login_id=session.login_id,
        role=session.role,
    )


class RoleIn(BaseModel):
    role: str


@router.post("/role", response_model=AuthOut)
def change_role(body: RoleIn, authorization: str = Header(default="")) -> AuthOut:
    """로그인한 계정의 역할을 바꾼다.

    앱은 역할별로 화면 트리가 완전히 갈린다 — 보호자 계정으로는 산책·제보 화면에
    갈 수 없다. 그런데 역할을 가입할 때 한 번만 고르게 해 두면, 잘못 고른 사람은
    계정을 새로 만드는 수밖에 없다(현장 실측 08-11). 여기서 바꿀 수 있게 한다.

    산책·제보 기록은 user_id 에 붙으므로 역할을 바꿔도 그대로 남는다.
    """
    token = authorization.removeprefix("Bearer ").strip()
    session = storage.sessions.get(token)
    if session is None:
        raise HTTPException(401, "다시 로그인해 주세요.")
    if body.role not in _ROLES:
        raise HTTPException(400, "역할이 올바르지 않습니다.")

    account = storage.accounts.get(session.user_id)
    if account is None:
        raise HTTPException(401, "다시 로그인해 주세요.")
    account.role = body.role
    storage.accounts.save(account.user_id, account)

    # 이 토큰이 들고 있던 역할도 함께 갱신한다 — 안 그러면 앱을 껐다 켤 때
    # 옛 역할로 되돌아간다(/auth/me 가 세션을 읽으므로).
    session.role = body.role
    storage.sessions.save(token, session)
    return AuthOut(token=token, user_id=account.user_id,
                   login_id=account.login_id, role=account.role)


@router.post("/logout")
def logout(authorization: str = Header(default="")) -> dict:
    """토큰을 서버에서 지운다 — 기기에서만 지우면 남은 토큰이 계속 유효하다."""
    token = authorization.removeprefix("Bearer ").strip()
    storage.sessions.delete(token)
    return {"ok": True}
