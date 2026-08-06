"""수색 안내 문구 다듬기 전용 LLM 클라이언트 — Mi:dm 2.0 Mini.

## 왜 EXAONE 이 아니라 Mi:dm 인가 (2026-08-06 결정)

이 작업이 필요로 하는 것은 **한국어 어조 하나뿐**이다. 넘어오는 것은 이미 템플릿이
만들고 검증까지 통과한 문장 하나이고, 할 일은 그걸 자연스럽게 다듬는 것이다 —
SAR 도메인 지식도, 구조화 출력도 쓰이지 않는다.

그런데 `exaone-sar` 는 SAR 파인튜닝본이다(논문 46편·QA 496개). 그 학습으로 얻은
지식과 형식이 여기서는 하나도 안 쓰인다. 반면 Mi:dm 은 Phase 0 에서 이미 같은
종류의 일을 하고 있다 — `midm.phrase_question()` 이 슬롯을 "자연스러운 존댓말
질문"으로 문장화한다.

부수 효과로 **마음 경로(`exaone-mind-dem3`)와 물리적으로 갈라진다.** 그쪽은 학습
형식과 문구가 봉인돼 있어(llm/mind_v2.py) 건드리면 어댑터 성능이 무효가 된다.

## 왜 Mini 인가
한 문장의 어조를 다듬는 일이다. 다턴 대화도, 긴 문맥도, 추론도 필요 없다 —
온보딩 대화용 Mi:dm(`midm_*`, Friendli dedicated)까지 끌어올 이유가 없고, 골든타임
경로라 응답이 빠른 쪽이 낫다. tip_llm 이 이미 Mini 를 서빙하고 있어 새 인프라도
필요 없다.

## 왜 tip_llm 에 얹지 않는가
같은 Mi:dm 서빙을 쓰지만 tip_llm 은 "시민 제보 구조화 **전용**"이라고 스스로
못박아 뒀고, 성격도 다르다 — 추출은 온도 0.1 로 사실을 뽑고 여기는 0.7 로 어조를
고른다. 실패 시 폴백도 다르다(그쪽은 휴리스틱, 여기는 템플릿 원문 그대로).

## 서빙
`copy_llm_*` 설정이 비면 `tip_llm_*` 를 그대로 물려받는다 — 둘 다 Phase 3 의 가벼운
1회성 한국어 작업이라, 나눌 이유가 생기기 전까지 엔드포인트를 둘 띄우는 건 낭비다.
셋 중 하나라도 비면 스텁(다듬지 않음)으로 떨어진다.
"""

from __future__ import annotations

import json
import urllib.request

from app.config import settings
from app.llm.base import LLMClient

#: 어조 축 — `persona_type` 을 **진단명 없이** 번역한 값.
#:
#: 🚨 persona_type 은 입력 전용이라 프롬프트에 넣는 것 자체는 허용되지만, 그래도
#: "치매"라는 단어를 모델에 주지 않는다. 받은 적 없는 것은 샐 수 없다 —
#: 이 모듈이 검증기(storytelling.validate)에만 기대지 않는 이유다.
_TONE = {
    "dementia": "고령의 어르신을 찾는 상황입니다. 차분하고 존중하는 어조로 쓰세요.",
}
_TONE_DEFAULT = "차분하고 존중하는 어조로 쓰세요."

_SYSTEM = """\
너는 실종자 수색 안내 문구를 다듬는다. 이 문구는 주변 시민이 앱에서 읽고 \
'어디를 봐야 할지' 판단하는 데 쓴다.

원문을 주면 **같은 내용을 더 자연스러운 한국어로** 고쳐 쓴다.

지켜야 할 것:
- 원문에 없는 장소·시간·상태를 절대 덧붙이지 않는다. 정보를 늘리는 게 아니라 \
말투만 다듬는 것이다.
- 원문에 있는 장소는 하나도 빼지 않는다.
- 실종자가 어디에 있다고 단정하지 않는다. "~계실 수 있어요", "~가능성이 있어요" \
처럼 가능성으로만 쓴다.
- 질환·장애·진단명을 쓰지 않는다.
- 시민에게 말하는 존댓말. 두 문장 이내, 120자 이내.
- 다듬은 문구 한 줄만 출력한다. 설명·따옴표·머리말을 붙이지 않는다."""


class CopyLLMClient(LLMClient):
    name = "수색 안내 문구 LLM (Mi:dm)"

    def __init__(self) -> None:
        super().__init__(settings.copy_llm_api_key or settings.tip_llm_api_key)
        base = settings.copy_llm_base_url or settings.tip_llm_base_url
        self.base_url = base.rstrip("/")
        self.model = settings.copy_llm_model or settings.tip_llm_model
        # 호출 실패 누적 — 폴백이 침묵하므로(원문 그대로) 장애 감지용.
        self.call_failures = 0

    @property
    def is_stub(self) -> bool:
        return not (self.api_key and self.base_url and self.model)

    # ── OpenAI 호환 chat completions ────────────────────────────────
    def _chat_url(self) -> str:
        base = self.base_url
        if base.endswith("/chat/completions"):
            return base
        if base.endswith("/v1"):
            return f"{base}/chat/completions"
        return f"{base}/v1/chat/completions"

    def chat(self, messages: list[dict], *, temperature: float, max_tokens: int = 200) -> str:
        payload = json.dumps({
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }).encode("utf-8")
        req = urllib.request.Request(
            self._chat_url(),
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=settings.llm_timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]

    def _call_api(self, prompt: str, **kwargs) -> str:
        return self.chat([{"role": "user", "content": prompt}], **kwargs)

    # ── 수색 안내 문구 ──────────────────────────────────────────────
    def refine(self, baseline: str, persona_type: str | None = None) -> str:
        """템플릿 문구 → 다듬은 문구. 실패·스텁이면 **원문 그대로** 돌려준다.

        ## 왜 원문을 주고 고쳐 쓰게 하나 (구조 자체가 방어선)
        페르소나를 주고 처음부터 짓게 하면 모델이 없는 장소·시간을 지어낼 재료를
        갖게 된다. 원문만 주면 그 재료가 아예 없다 — 프롬프트 준수가 아니라
        **입력 부족**이 안전을 보장한다(storytelling 모듈 전체의 원칙).

        반환값은 아직 검증 전이다. 호출부가 storytelling.validate() 를 통과시켜야
        한다 — 검증기를 여기 두면 llm 계층이 phase3 를 알아야 해서 층이 뒤집힌다.
        """
        if self.is_stub or not baseline:
            return baseline
        try:
            raw = self.chat(
                [
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": (
                        f"{_TONE.get(persona_type or '', _TONE_DEFAULT)}\n\n"
                        f"[원문]\n{baseline}"
                    )},
                ],
                temperature=settings.copy_llm_temp,
                max_tokens=200,
            )
        except Exception:  # noqa: BLE001 — 안내가 없다고 수색 화면이 깨지면 안 된다
            self.call_failures += 1
            return baseline
        return clean_line(raw) or baseline


#: 모델이 지시를 어기고 붙이는 메타 머리말. **알려진 것만** 벗긴다.
#:
#: 한때 "콜론 앞이 10자 이하면 머리말"로 잡았는데, "지금 시각 기준: 최종 목격
#: 장소를…" 같은 멀쩡한 문장의 앞부분을 잘라먹었다(테스트가 잡음). 휴리스틱보다
#: 목록이 안전하다 — 못 벗긴 머리말은 어색할 뿐이지만, 잘못 벗기면 내용이 사라진다.
_META_PREFIXES = ("다듬은 문구", "다듬은 문장", "수정된 문구", "출력", "결과", "답변", "안내 문구")


def clean_line(raw: str) -> str:
    """모델 출력에서 문구 한 줄만 추출.

    지시를 어기고 머리말이나 따옴표를 붙이는 경우가 흔해서, 형식 위반으로 통째로
    버리기보다 여기서 벗겨낸다 — 내용이 멀쩡한데 껍데기 때문에 폴백하면 LLM 을
    붙인 의미가 없다.
    """
    text = (raw or "").strip()
    if not text:
        return ""
    # 여러 줄이면 내용이 있는 첫 줄만. 모델이 설명을 덧붙이는 경우 대응.
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        for prefix in _META_PREFIXES:
            if line.startswith(prefix):
                head, sep, tail = line.partition(":")
                # 콜론 뒤에 본문이 있을 때만 — "출력이 없어요" 같은 문장 보호.
                if sep and tail.strip() and len(head) <= len(prefix) + 2:
                    line = tail.strip()
                break
        return line.strip().strip('"').strip("'").strip()
    return ""
