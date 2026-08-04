# 임베더 교체 실험 (KURE → SKT/Upstage)

Phase0 슬롯 매칭·Phase2 RAG가 쓰는 임베더를 KURE-v1에서 국내 대기업 임베더로
바꾸기 위한 비교 실험. 측정 전체 설계·해석·개인정보 검토는 노션
[「임베더 교체 실험 — 처음부터 차근차근」](https://www.notion.so/3b109d8976be812d9269ed2776b2a142)
참고 — 여기는 코랩에서 돌린 코드를 재현 가능하게 옮겨놓은 것이다.

슬롯 적중률 측정은 이 폴더가 아니라 `experiments/slot_ranking/slot_sim_dist.py`
(임베더 인자만 바꿔 실행, 로컬 CPU로 충분).

## 왜 코랩(GPU)인가

슬롯 측정은 후보가 12개뿐이라 로컬 CPU로 충분하지만, 이 폴더의 두 스크립트는 다르다.

- `train_skt.py`: 파인튜닝 자체가 GPU 없인 매우 느림.
- `rag_recall.py`: 논문 청크 2,488개를 매번 다시 벡터화해야 한다(인덱스에 저장된
  KURE 벡터는 재사용하지 않고 텍스트만 꺼내 쓴다 — 임베더별로 공정 비교하려면
  그래야 한다). 로컬 CPU로는 느리다.

## 구성

```
split_data.py   QA 493쌍을 train_use(396)/test(50)로 분리 (seed=0, val은 이미 분리돼 있음)
train_skt.py    SKT A.X-Encoder-base를 sar QA로 파인튜닝 → axencoder-sar-ft
rag_recall.py   임베더별 RAG Recall@1/@4 측정 (로컬 모델 또는 Upstage API)
```

## 실행 (코랩)

```bash
!pip -q install "sentence-transformers>=3.0" "transformers>=4.48" accelerate

# 0. 데이터 준비 (train.jsonl·val.jsonl을 먼저 업로드)
python -m experiments.embedder_swap.split_data --train train.jsonl

# 1. SKT 파인튜닝
python -m experiments.embedder_swap.train_skt

# 2. RAG Recall 측정 (rag_index.npz·test.jsonl을 먼저 업로드)
python -m experiments.embedder_swap.rag_recall --model axencoder-sar-ft
python -m experiments.embedder_swap.rag_recall --model skt/A.X-Encoder-base   # 튜닝 전 원본, 비교용
python -m experiments.embedder_swap.rag_recall --model nlpai-lab/KURE-v1

python -m experiments.embedder_swap.rag_recall --upstage   # UPSTAGE_API_KEY 환경변수 필요
```

## 결과 (2026-08-04)

| 지표 | SKT(원본) | SKT(파인튜닝) | Upstage | KURE(참고) |
|---|---|---|---|---|
| 슬롯 적중률 | 44.8% | 69.0% | 96.6% | 93.1% |
| RAG Recall@4 | 8.0% | 22.0% | 80.0% | 76.0% |

Upstage가 두 지표 모두 1등. SKT는 튜닝으로 방향은 맞게 개선됐으나(슬롯 44.8→69.0%,
RAG 8.0→22.0%) 스케일이 큰 RAG(후보 2,538개)일수록 KURE·Upstage와의 격차가 더
벌어졌다 — 396개·3epoch 소규모 튜닝으로는 대규모 후보군에 필요한 구분력까지는
못 만든 것으로 보인다.

Upstage 채택 시 개인정보(온보딩 발화가 외부로 전송됨, 국외이전 명시 확인됨) 검토가
필요 — 노션 문서의 "개인정보 검토" 섹션 참고. 가장 민감한 데이터(슬롯 매칭에 쓰이는
보호자 발화)는 로컬 임베더(KURE)로 유지하고 RAG(논문 검색, 상대적으로 저위험)만
Upstage로 분리하는 하이브리드 구성이 현실적인 완화책으로 검토됨.
