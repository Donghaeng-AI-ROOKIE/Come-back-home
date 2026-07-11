"""LG EXAONE 엔드포인트 프로브 — OpenAI 호환 여부/형식 확인.

앱 임포트·외부 패키지 없이 stdlib 만으로 한 번 호출해 본다.
크리덴셜은 '환경변수'로 넘긴다(채팅/코드에 비밀키를 넣지 않기 위해).

실행:
  EXAONE_BASE_URL="<endpoint URL>" \
  EXAONE_MODEL="<endpoint ID>" \
  EXAONE_API_KEY="<API key>" \
  python3 scripts/probe_exaone.py

BASE_URL 은 '…/v1' 까지(끝에 /chat/completions 붙임) 또는 '…/chat/completions'
전체를 넣어도 됨. 아래는 둘 다 시도한다.
"""

import json
import os
import urllib.error
import urllib.request

BASE = os.environ.get("EXAONE_BASE_URL", "").rstrip("/")
MODEL = os.environ.get("EXAONE_MODEL", "")
KEY = os.environ.get("EXAONE_API_KEY", "")

if not (BASE and MODEL and KEY):
    raise SystemExit("환경변수 EXAONE_BASE_URL / EXAONE_MODEL / EXAONE_API_KEY 를 모두 설정하세요.")

# base 가 이미 완결 경로면 그대로, 아니면 /chat/completions 를 붙여 시도
candidates = [BASE] if BASE.endswith("/chat/completions") else [
    f"{BASE}/chat/completions",
    f"{BASE}/v1/chat/completions",
]

payload = {
    "model": MODEL,
    "messages": [
        {"role": "system", "content": "너는 간결한 한국어 비서다."},
        {"role": "user", "content": "한 문장으로 자기소개 해줘."},
    ],
    "temperature": 0.3,
    "max_tokens": 128,
}

for url in candidates:
    print(f"\n── POST {url}")
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {KEY}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            print(f"   HTTP {resp.status}")
            try:
                data = json.loads(body)
                msg = data.get("choices", [{}])[0].get("message", {}).get("content")
                print("   ✅ OpenAI 호환 확인. 모델 응답:")
                print("   ", (msg or "(content 필드 없음 — 아래 원문 참고)"))
                print("   ── 응답 상위 키:", list(data.keys()))
            except json.JSONDecodeError:
                print("   ⚠️ JSON 아님 — 원문 앞부분:")
                print("   ", body[:500])
            break
    except urllib.error.HTTPError as e:
        print(f"   HTTP {e.code} {e.reason}")
        print("   ", e.read().decode("utf-8", "replace")[:500])
    except Exception as e:  # noqa: BLE001
        print(f"   ✖ 연결 실패: {type(e).__name__}: {e}")
