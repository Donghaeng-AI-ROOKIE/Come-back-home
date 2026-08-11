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
