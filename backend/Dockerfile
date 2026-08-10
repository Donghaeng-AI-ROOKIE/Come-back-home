# 돌아오길 백엔드 — API + 대시보드(/dashboard, 정적 HTML 포함) 단일 이미지.
#
# 배포 단위 정리 (2026-08-07):
#   - 대시보드는 별도 앱이 아니다. FastAPI 가 app/static/dashboard.html 을
#     서빙하므로 이 이미지 하나로 API·대시보드가 함께 배포된다.
#   - 모바일 앱(Expo)은 서버 배포 대상이 아니라 클라이언트 빌드(EAS)다.
#
# ⚠ EXAONE 게이트웨이는 Tailscale 사설망(100.73.27.46:18000)이다.
#   배포 호스트가 태일넷에 조인돼 있어야 모델 실호출이 된다 — 아니면
#   EXAONE 경로만 조용히 스텁으로 떨어진다(예측은 통계 폴백으로 계속 돌아
#   화면만 봐서는 모른다. /phase3 응답의 prior_source 로 확인할 것).
#   Mi:dm(FriendliAI)·Upstage 는 공인 API 라 무관.

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 의존성 레이어 — 소스보다 먼저 복사해 캐시를 살린다 (지오 스택이 무겁다).
# sentence-transformers 는 제외한다: torch 를 끌고 와 이미지가 2~3GB 가 되는데
# 운영 임베더는 Upstage 원격(EMBED_BASE_URL)이라 컨테이너에서 쓰이지 않는다.
# 로컬 임베더 폴백이 필요한 환경이면 이 줄을 지우고 빌드할 것.
# pytest 는 런타임 불필요.
COPY requirements.txt .
RUN grep -vE '^(sentence-transformers|pytest)' requirements.txt > /tmp/req.txt \
    && pip install -r /tmp/req.txt

# 앱 소스만 — experiments/tests 는 이미지에 넣지 않는다 (크기·정보 최소화)
COPY app/ app/
COPY scripts/ scripts/

# 상태는 전부 /app/data 아래 (config 기본값과 일치):
#   storage.db(SQLite 영속화) · roadnet_cache/ · audit_log.jsonl(개인정보 감사)
# 반드시 볼륨으로 마운트할 것 — 5일 파기(개인정보보호법 §21)가 컨테이너
# 재생성에도 유지되는 실제 디스크에 닿아야 한다.
VOLUME /app/data

EXPOSE 8000

# 워커 1 고정: 인메모리 Repository + SQLite(journal_mode=DELETE) 전제라
# 다중 워커면 케이스 상태가 워커마다 갈라진다. 스케일아웃은 저장소 공유화 후.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
