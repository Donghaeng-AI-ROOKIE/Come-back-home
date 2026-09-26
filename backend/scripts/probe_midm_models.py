"""KT 믿음 API — `model` 필드 후보를 한 번에 쳐보는 프로브.

배경(2026-09-26): 결선용 Mi:dm 2.5 Pro 키는 endpoint(https://midm.kt.com/v1/chat/completions)
와 키만 안내되고 모델 ID 가 없다. 인증은 통과하는데(`4203` 아님) `4400 요청 대상을 찾을 수
없습니다` 만 돌아와서, 게이트웨이가 `model` 값으로 대상을 찾는 것으로 추정 → 후보 순회.

키는 환경변수로만 받고 절대 출력하지 않는다.

실행(cmd):
  set MIDM_API_KEY=<키>
  .venv/Scripts/python scripts/probe_midm_models.py
  .venv/Scripts/python scripts/probe_midm_models.py 추가후보1 추가후보2   # 후보 덧붙이기

성공(choices 수신)하면 그 자리에서 멈추고 모델명을 출력한다.
"""

import json
import os
import sys
import urllib.error
import urllib.request

# cmd 기본 코드페이지(CP949)에서 한글 출력이 깨지지 않게
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

URL = os.environ.get("MIDM_BASE_URL", "https://midm.kt.com/v1/chat/completions")
KEY = os.environ.get("MIDM_API_KEY", "")
if not KEY:
    raise SystemExit("환경변수 MIDM_API_KEY 를 설정하세요 (set MIDM_API_KEY=...).")

# 표시명 "믿:음 2.5 Pro", 벤치마크 등재명 "Mi:dm K 2.5 Pro", 2.0 HF 명명 규칙
# (K-intelligence/Midm-2.0-Base-Instruct)을 조합한 후보. 앞쪽이 유력.
CANDIDATES = [
    "midm-2.5-pro",
    "Midm-2.5-Pro",
    "midm-k-2.5-pro",
    "Midm-K-2.5-Pro",
    "midm-2.5-pro-preview",
    "midm-k-2.5-pro-preview",
    "K-intelligence/Midm-2.5-Pro",
    "K-intelligence/Midm-K-2.5-Pro",
    "midm-2.5",
    "midm-pro",
    "midm",
    "mi:dm-2.5-pro",
    "Mi:dm 2.5 Pro",
    "Mi:dm K 2.5 Pro",
    "믿:음 2.5 Pro",
    "믿음 2.5 Pro",
    "믿:음2.5Pro",
]
CANDIDATES += [a for a in sys.argv[1:] if a not in CANDIDATES]


def call(model: str):
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "Introduce yourself in one sentence."}],
        "max_tokens": 32,
        "temperature": 0.0,
    }
    req = urllib.request.Request(
        URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


print(f"POST {URL}\n")
for model in CANDIDATES:
    status, text = call(model)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = None
    if data and data.get("choices"):
        content = data["choices"][0].get("message", {}).get("content")
        print(f"✅ {model!r}  HTTP {status}")
        print(f"   응답: {content!r}")
        print(f"   응답 model 필드: {data.get('model')!r}")
        print(f"\n→ .env 에 MIDM_MODEL={model}")
        break
    err = (data or {}).get("error", {}) if isinstance(data, dict) else {}
    code = err.get("code", "")
    msg = err.get("message", text[:120].replace("\n", " "))
    print(f"✖ {model!r:36}  HTTP {status}  code={code}  {msg}")
else:
    print("\n모든 후보 실패 — 게이트웨이가 model 로 대상을 찾는 게 아니거나(키에 배포 미연결),"
          " 이름이 후보 밖. 운영진 문의 필요.")
