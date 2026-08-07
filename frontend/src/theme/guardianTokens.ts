/**
 * 보호자 모드 전용 팔레트 (피그마 AI Rookie_돌아오길 [보호자] 프레임 확정본).
 *
 * tokens.ts 의 색은 "상태 심각도"를 부호화한다 — 보호자 모드는 그 위에
 * "평시 안심(그린)" 브랜드 톤을 얹는다. 시민 수색·긴급 트리는 건드리지 않고
 * 보호자 화면에서만 이 팔레트를 쓴다.
 */
export const gColor = {
  primary: '#67AE6E', // 활성 탭·포인트 (피그마 홈 탭)
  cardGreen: '#90C67C', // 안심 사전 등록 카드
  alertRed: '#F14444', // 실종 신고 원형 버튼
  textMuted: '#525253', // 카드 본문·안내 불릿
  gray: '#909090', // 비활성 탭·보조 라벨
  barBg: '#F8F8F8', // 섹션 헤더·행 배경 (Backgrounds / Bars - Light Gray)
  chip: '#D9D9D9', // 치매 정도 등 상태 칩
  surface: '#FFFFFF',
  inkGreen: '#316837', // 키-값 행의 키 라벨 (등록 상세)
  textValue: '#4D4D4D', // 키-값 행의 값
  backGray: '#8E8E93', // 뒤로가기 화살표 (Graybase / Gray 1)
  mint: '#ECFAE5', // 완료·챗봇 화면 배경
  progressGreen: '#328E6E', // 진행 단계·안내 제목 그린
  bubbleBot: '#DDF6D2', // 챗봇(어시스턴트) 말풍선
  bubbleUser: '#EDEDED', // 사용자 말풍선
  track: '#E5E5EA', // 진행바 비활성 트랙 (Graybase / Gray 4)
  quickRed: '#E05454', // 빠른 등록(미등록 긴급 인터뷰) 포인트
  bubbleBotQuick: 'rgba(224,84,84,0.44)', // 빠른 등록 봇 말풍선
} as const;

/** 하단 탭바 — 흰 바탕, 위 모서리 라운드, 위쪽 그림자 (Glassmorphism Background). */
export const gTabBar = {
  radius: 40,
  height: 84,
} as const;
