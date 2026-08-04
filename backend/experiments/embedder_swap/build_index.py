"""기존 rag_index.npz의 청크 텍스트를 재사용해, 현재 설정된 임베더(Upstage
embedding-passage)로 재벡터화한 새 인덱스를 만든다.

왜 필터링도 같이 하는가:
  발달장애 페르소나는 PR#110으로 앱 코드에서 제거됐지만(치매 단독 서비스),
  이 논문 코퍼스는 그때 안 걸러졌다 — cls 필드 집계 결과 2,488개 중 발달장애가
  1,288개(51.8%). 치매 단독인데 검색 후보 절반이 무관한 발달장애 논문이면
  정확도가 깎이므로, 여기서 cls가 "치매"로 시작하는 것만 남긴다(화이트리스트 —
  "발달장애만 뺀다"가 아니라 "치매만 남긴다"라서, 제3의 분류가 섞여도 기본적으로
  제외돼 더 안전하다).

기존 인덱스는 덮어쓰지 않는다 — 검증 전까지 롤백 가능하게 새 파일로 저장한다.
get_embedder()를 그대로 써서, 실제 앱이 Phase0에서 쓰는 것과 동일한 임베더로
만든다(설정 하나로 통일).

사용 (backend 디렉토리에서, .env에 Upstage 설정이 있는 상태로):
  PYTHONUTF8=1 PYTHONPATH=. python -m experiments.embedder_swap.build_index
"""

from __future__ import annotations

import argparse
import json

import numpy as np


def main() -> int:
    ap = argparse.ArgumentParser(description="RAG 인덱스를 현재 임베더로 재생성(치매 논문만)")
    ap.add_argument("--input", default="data/rag_index.npz")
    ap.add_argument("--output", default="data/rag_index_upstage.npz")
    ap.add_argument("--cls-prefix", default="치매", help="이 접두어로 시작하는 cls만 남긴다")
    ap.add_argument("--batch", type=int, default=100, help="API 임베더 요청당 텍스트 수")
    args = ap.parse_args()

    from app.config import settings
    from app.phase0.retrieval import get_embedder

    z = np.load(args.input, allow_pickle=True)
    meta = json.loads(str(z["meta"]))
    before = len(meta)
    kept = [m for m in meta if str(m.get("cls", "")).startswith(args.cls_prefix)]
    after = len(kept)
    print(f"필터링: {before}개 → {after}개 ('{args.cls_prefix}'만 유지, {before - after}개 제외)")
    if not kept:
        print("남은 청크가 없다 — cls-prefix 확인 필요")
        return 1

    emb = get_embedder()
    texts = [m["text"] for m in kept]
    print(f"임베더: {type(emb).__name__}")
    # OpenAICompatEmbedder는 배치를 안 나눠서(Phase0에선 소량 호출뿐이라 필요 없었음),
    # 여기서는 요청 크기·타임아웃 문제를 피하려고 직접 나눠 보낸다.
    vec_batches = []
    for i in range(0, len(texts), args.batch):
        batch = texts[i : i + args.batch]
        vec_batches.extend(emb.encode(batch, role="passage"))
        print(f"  {min(i + args.batch, len(texts))}/{len(texts)}")
    vecs = np.asarray(vec_batches, dtype="float32")

    if settings.embed_base_url:
        model_id = f"{settings.embed_base_url}:{settings.embed_model_passage or settings.embed_model}"
    else:
        model_id = settings.embed_model or "hash-stub"

    np.savez(
        args.output,
        vecs=vecs,
        meta=json.dumps(kept, ensure_ascii=False),
        model=model_id,
    )
    print(f"저장됨: {args.output} ({after}개 청크, {vecs.shape[1]}차원, model={model_id})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
