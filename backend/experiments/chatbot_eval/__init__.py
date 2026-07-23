"""챗봇 성능 평가 하네스 (Phase 0 온보딩 엘리시테이션).

axis_goldset(축 점수 채점 실험)과 **완전 별개**다. 여기서 재는 것은 축 점수가
아니라 대화 챗봇이 보호자 답변에서 페르소나를 얼마나 잘 뽑아내는가 —
끌림점 재현율 · evidence 등급 정확도 · 축 근거 커버리지 · 질문 효율.

구성:
  scenarios.py  — 보호자 답변 대본 + 기대 페르소나 쌍 (시나리오 뱅크)
  responder.py  — 챗봇 질문을 읽고 대본에서 답을 고르는 질문-매칭기
  runner.py     — TestClient 로 세션을 끝까지 굴려 Transcript 수집
  scorer.py     — Transcript × 기대치 → ScoreCard (5지표)
  run_eval.py   — 엔트리포인트 (드라이런 / --go / --real)

최종 목적: 대화 가드 6종을 하나씩 꺼보며 점수 변화로 실효성 측정("가드 다이어트").
"""
