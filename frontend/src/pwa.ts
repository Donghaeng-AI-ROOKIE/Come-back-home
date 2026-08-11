/**
 * PWA 등록 — 홈 화면에 "앱"으로 설치되게 하고, 서비스 워커를 올린다.
 *
 * Expo 웹 내보내기는 index.html 을 자동 생성하므로 태그를 소스로 넣을 자리가 없다.
 * 그래서 부팅 시점에 head 에 직접 붙인다. 사용자가 "홈 화면에 추가"를 누르는 것은
 * 페이지가 뜬 뒤이므로, 그때 DOM 에 있으면 아이콘·이름·standalone 이 반영된다.
 *
 * 서비스 워커를 여기서 미리 올리는 이유: 알림 권한을 누르는 순간에 처음 등록하면
 * 활성화를 기다리다 실패할 수 있다. 워커 등록 자체는 권한과 무관하고 조용하다.
 */
import { Platform } from 'react-native';

function meta(attrs: Record<string, string>) {
  const el = document.createElement('meta');
  Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, v));
  document.head.appendChild(el);
}

function link(attrs: Record<string, string>) {
  const el = document.createElement('link');
  Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, v));
  document.head.appendChild(el);
}

/**
 * 폰 폭에 맞춰 화면 전체를 비례 조정한다.
 *
 * 시안이 **375pt 폭 절대좌표**로 그려져 있어(top/left 를 px 로 박아 둔 화면이 많다)
 * 폭이 다른 폰에서는 여백이 남거나 요소가 밀린다. 좌표를 전부 상대값으로 바꾸는 대신
 * 375 캔버스를 통째로 확대·축소한다 — 시안 비율이 어떤 기기에서도 그대로 유지된다.
 *
 * 높이는 배율만큼 되돌려 준다(100dvh / s). 안 그러면 확대한 만큼 아래가 잘려
 * 하단 탭바가 화면 밖으로 나간다.
 */
function scaleToPhone(): void {
  const BASE = 375;
  const root = document.getElementById('root');
  if (!root) return;

  /**
   * 키보드가 올라온 만큼 줄어든 **실제로 보이는 높이**.
   *
   * 웹에서는 KeyboardAvoidingView 가 동작하지 않는다(iOS 네이티브 전용). 그래서
   * 키보드가 올라와도 앱 높이는 그대로였고, 입력칸과 탭바가 키보드 뒤로 들어가
   * 챗봇 화면이 통째로 어긋났다(현장 제보 08-11 — 온보딩 챗봇).
   * visualViewport 는 키보드를 뺀 영역을 알려 주므로 그 값에 앱을 맞춘다.
   */
  const visibleH = () => window.visualViewport?.height ?? window.innerHeight;

  const apply = () => {
    const w = window.innerWidth;
    // 폭이 0 이거나 비정상적으로 작을 때가 있다(레이아웃 전·숨은 탭). 그때
    // 배율을 계산하면 scale(0) 이 되어 **화면이 통째로 사라진다.** 그냥 건너뛴다.
    if (!Number.isFinite(w) || w < 240) return;
    // 데스크톱에서까지 늘리면 거대해진다 — 폰 범위(≤560px)에서만 맞춘다.
    // 배율은 안전 범위로 자른다(너무 작게·크게 그리지 않는다).
    const s = w <= 560 ? Math.min(Math.max(w / BASE, 0.7), 1.6) : 1;
    const h = visibleH();
    if (s === 1) {
      root.style.removeProperty('width');
      root.style.removeProperty('transform');
      root.style.removeProperty('transform-origin');
      // 배율을 안 쓰더라도 키보드 높이는 반영해야 한다.
      root.style.height = `${h}px`;
      root.style.maxHeight = `${h}px`;
      return;
    }
    root.style.width = `${BASE}px`;
    // 위 <style> 의 `max-height: 100dvh` 가 확대된 높이를 그대로 잘라 버린다
    // (실측: 320폭에서 666px 로 잡혀야 할 높이가 568px 로 깎여 아래가 비었다).
    // 인라인으로 함께 덮어쓴다.
    root.style.height = `${h / s}px`;
    root.style.maxHeight = `${h / s}px`;
    root.style.transformOrigin = 'top left';
    root.style.transform = `scale(${s})`;
  };

  apply();
  window.addEventListener('resize', apply);
  window.addEventListener('orientationchange', apply);
  // 키보드 열림·닫힘은 여기로만 온다(resize 가 안 오는 기기가 있다).
  window.visualViewport?.addEventListener('resize', apply);
  window.visualViewport?.addEventListener('scroll', apply);
}

export function setupPwa(): void {
  if (Platform.OS !== 'web' || typeof document === 'undefined') return;
  if (document.querySelector('link[rel="manifest"]')) return;   // 중복 방지

  // 모바일 브라우저 툴바가 하단 탭바를 덮는 문제.
  //
  // 사파리·크롬의 주소창/툴바는 화면 아래를 차지하는데, 기본 100vh 는 그 영역까지
  // 포함한 높이다. 그래서 앱의 탭바가 툴바 뒤로 들어가 **눌러도 브라우저가 먹는다**
  // (실측 08-11: "탭이 안 눌린다"). 100dvh 는 지금 실제로 보이는 높이라 이 문제가 없다.
  // 홈 화면에 설치해 열면 툴바가 없어 어차피 같은 값이 된다.
  const style = document.createElement('style');
  style.textContent = `
    html, body, #root { height: 100dvh; max-height: 100dvh; }
    @supports not (height: 100dvh) { html, body, #root { height: 100vh; } }

    /* 홈 인디케이터(아이폰 아래쪽 가로 막대) 영역만큼 앱을 위로 올린다.
       탭바는 높이 85px 고정이고 안전영역을 스스로 처리하지 않는다 —
       viewport-fit=cover 로 화면 끝까지 그리게 했으므로 여기서 빼 주지 않으면
       탭 라벨 아래쪽이 인디케이터에 가려 **잘려 보인다**(실측 08-11 제보).
       env() 를 모르는 브라우저는 0 이라 기존과 동일하다. */
    #root {
      box-sizing: border-box;
      padding-bottom: env(safe-area-inset-bottom, 0px);
    }
  `;
  document.head.appendChild(style);

  // 노치 영역까지 그리되 안전영역은 존중한다 — 위 dvh 와 함께 써야 의미가 있다.
  const vp = document.querySelector('meta[name="viewport"]');
  if (vp && !(vp.getAttribute('content') || '').includes('viewport-fit')) {
    vp.setAttribute('content', `${vp.getAttribute('content')}, viewport-fit=cover`);
  }

  link({ rel: 'manifest', href: '/manifest.json' });
  // iOS 는 매니페스트만으로 부족하다 — 아래 세 태그가 있어야 홈 화면 아이콘이
  // 브라우저 UI 없이(standalone) 열리고, 그래야 웹 푸시가 허용된다.
  link({ rel: 'apple-touch-icon', href: '/icon-192.png' });
  meta({ name: 'apple-mobile-web-app-capable', content: 'yes' });
  meta({ name: 'apple-mobile-web-app-title', content: '돌아오길' });
  meta({ name: 'apple-mobile-web-app-status-bar-style', content: 'default' });
  meta({ name: 'theme-color', content: '#328E6E' });

  scaleToPhone();

  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch((e) => {
      // 실패해도 앱은 그대로 돈다 — 알림만 못 받는다.
      console.warn('[pwa] 서비스 워커 등록 실패:', e);
    });
  }
}
