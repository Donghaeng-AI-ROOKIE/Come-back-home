"""RAG 검색기 테스트 — 인덱스가 없어도 예측이 죽지 않는 것이 핵심 계약."""

import json

import numpy as np
import pytest

from app.config import settings
from app.rag.retriever import Passage, Retriever, format_block


def _write_index(path, rows, model="test-embedder"):
    """행 = (source, text, vec). 벡터는 정규화해서 넣는다(코사인 전제)."""
    vecs = np.array([v for _, _, v in rows], dtype="float32")
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    meta = [{"kind": "paper", "source": s, "text": t, "grade": "A",
             "cls": "치매/SAR", "desc": "", "i": i}
            for i, (s, t, _) in enumerate(rows)]
    np.savez_compressed(path, vecs=vecs.astype("float16"),
                        meta=json.dumps(meta, ensure_ascii=False), model=model)


class _FakeEmbedder:
    """질의를 고정 벡터로 — 검색 로직만 보고 임베딩 품질은 보지 않는다."""

    def __init__(self, vec):
        self.vec = vec

    def encode(self, texts, role: str = "query"):
        return [self.vec for _ in texts]


def _ready(path, qvec, model="test-embedder"):
    r = Retriever(str(path), model)
    assert r.available
    r._embedder = _FakeEmbedder(qvec)
    return r


def test_인덱스가_없으면_조용히_비활성(tmp_path):
    """파일 부재가 예외로 번지면 데모 중 예측 전체가 멈춘다."""
    r = Retriever(str(tmp_path / "없는파일.npz"))
    assert r.available is False
    assert r.search("치매 배회") == []


def test_손상된_인덱스도_예외를_밖으로_내보내지_않는다(tmp_path):
    bad = tmp_path / "broken.npz"
    bad.write_bytes("이건 npz 가 아니다".encode("utf-8"))
    r = Retriever(str(bad))
    assert r.available is False
    assert r.search("치매 배회") == []


def test_유사도_상위를_반환한다(tmp_path):
    idx = tmp_path / "i.npz"
    _write_index(idx, [
        ("A", "가" * 300, [1.0, 0.0]),
        ("B", "나" * 300, [0.0, 1.0]),
    ])
    r = _ready(idx, [1.0, 0.0])
    hits = r.search("질의", top_k=1)
    assert [h.source for h in hits] == ["A"]


def test_출처당_상한이_top_k_독식을_막는다(tmp_path):
    """한 논문이 상위를 쓸어가면 근거의 폭이 좁아진다."""
    idx = tmp_path / "i.npz"
    rows = [("A", f"에이{i}" * 100, [1.0, 0.01 * i]) for i in range(5)]
    rows.append(("B", "비" * 300, [0.9, 0.1]))
    _write_index(idx, rows)
    r = _ready(idx, [1.0, 0.0])
    hits = r.search("질의", top_k=4)
    assert sum(h.source == "A" for h in hits) <= settings.rag_max_per_source
    assert "B" in {h.source for h in hits}


def test_같은_질의는_캐시에서_나온다(tmp_path):
    """mind 재해석이 케이스당 최대 10회 호출되므로 재검색이 그대로 지연이 된다."""
    idx = tmp_path / "i.npz"
    _write_index(idx, [("A", "가" * 300, [1.0, 0.0])])
    r = _ready(idx, [1.0, 0.0])
    first = r.search("같은 질의")

    class _Boom:
        def encode(self, texts, role: str = "query"):
            raise AssertionError("캐시가 있으면 임베딩을 다시 하면 안 된다")

    r._embedder = _Boom()
    assert r.search("같은 질의") == first


def test_임베더_불일치는_인덱스_쪽을_따른다(tmp_path, caplog):
    """질의와 문서가 다른 모델이면 코사인이 의미를 잃는데 조용히 나빠지기만 한다."""
    idx = tmp_path / "i.npz"
    _write_index(idx, [("A", "가" * 300, [1.0, 0.0])], model="인덱스모델")
    r = Retriever(str(idx), "설정모델")
    assert r.available
    assert r._model_name == "인덱스모델"


def test_빈_발췌는_블록을_만들지_않는다():
    assert format_block([]) == ""


def test_블록에_길이_상한이_걸린다():
    ps = [Passage(text="가" * 5000, source="A", kind="paper", score=0.9)]
    block = format_block(ps, max_chars=500)
    assert "[참고 지식]" in block
    assert len(block) < 900          # 안내문 + 상한만큼의 본문


def test_상한을_넘겨_토막만_남으면_넣지_않는다():
    ps = [Passage(text="가" * 400, source="A", kind="paper", score=0.9),
          Passage(text="나" * 400, source="B", kind="paper", score=0.8)]
    block = format_block(ps, max_chars=430)
    # 30자 토막은 근거가 못 되므로 두 번째 발췌는 통째로 빠진다 (불릿 1개만)
    assert len([ln for ln in block.splitlines() if ln.startswith("- ")]) == 1


@pytest.mark.parametrize("enabled", [True, False])
def test_설정으로_끄면_검색기를_주지_않는다(enabled, monkeypatch):
    from app.rag import retriever as mod

    monkeypatch.setattr(settings, "rag_enabled", enabled)
    monkeypatch.setattr(mod, "_singleton", None)
    got = mod.get_retriever()
    assert (got is not None) is enabled
