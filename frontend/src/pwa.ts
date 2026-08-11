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

  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch((e) => {
      // 실패해도 앱은 그대로 돈다 — 알림만 못 받는다.
      console.warn('[pwa] 서비스 워커 등록 실패:', e);
    });
  }
}
