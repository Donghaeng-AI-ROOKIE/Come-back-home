"""계정 — 아이디/비밀번호 로그인.

## 왜 계정이 필요해졌나
산책 기록·제보 참여·등급이 전부 `user_id` 로 갈리는데, 앱이 모두에게 같은
`demo-citizen` 을 보내고 있었다. 그래서 누가 켜도 남의 산책 횟수가 보였다.
아이디를 받으면 그 사람 것만 보인다.

## 비밀번호는 되돌릴 수 없게 저장한다
`hashlib.scrypt` (표준 라이브러리) + 계정마다 다른 salt. 원문은 어디에도 남기지
않고 서버 로그에도 찍지 않는다. 새 의존성을 들이지 않은 것은 배포 이미지를
그대로 쓰기 위해서다.

## 여기 담지 않는 것
실명·연락처·주소를 받지 않는다. 계정에 필요한 최소치는 "이 사람이 다시 왔다"를
아는 것뿐이고, 그건 아이디 하나로 충분하다. 표시 이름은 아이디를 그대로 쓴다.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class Account(BaseModel):
    """저장되는 계정 1건. **password_hash 는 앱으로 나가지 않는다**(api/auth.py)."""

    user_id: str          # 내부 식별자 — 산책·제보 기록의 키
    login_id: str         # 사용자가 입력하는 아이디(소문자 정규화)
    role: str             # 'citizen' | 'guardian'
    password_hash: str    # scrypt(hex)
    password_salt: str    # 계정별 난수(hex)
    created_at: datetime = Field(default_factory=datetime.now)


class Session(BaseModel):
    """로그인 토큰 → 계정. 만료는 두지 않는다 — 현장에서 갑자기 튕기면 안 된다."""

    token: str
    user_id: str
    login_id: str
    role: str
    created_at: datetime = Field(default_factory=datetime.now)
