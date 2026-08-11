/**
 * 서비스 워커 — 앱이 꺼져 있어도 경보를 띄운다.
 *
 * 이 파일이 없으면 웹 푸시가 성립하지 않는다. 브라우저는 앱이 아니라 **이 워커**를
 * 깨워서 알림을 그리기 때문이다. 그래서 여기서는 UI 코드를 부르지 않고, 받은
 * 페이로드로 알림 하나를 띄우는 일만 한다.
 *
 * 번들러를 거치지 않는 정적 파일이다(public/ → 배포 루트). import 를 쓰지 않는다.
 */

self.addEventListener('install', (event) => {
  // 새 워커를 즉시 활성화한다 — 알림 코드를 고쳤는데 옛 워커가 계속 도는 일을 막는다.
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('push', (event) => {
  let payload = {};
  try {
    payload = event.data ? event.data.json() : {};
  } catch (e) {
    // 형식이 깨져도 알림 자체는 띄운다 — 실종 경보를 통째로 삼키지 않는다.
    payload = { title: '실종 경보', body: '앱에서 확인해 주세요.' };
  }

  const title = payload.title || '실종 경보';
  const options = {
    body: payload.body || '주변에서 실종자를 찾고 있습니다.',
    // 아이콘이 없으면 브라우저 기본 아이콘이 뜬다 — 잠금화면에서 무슨 앱인지 모른다.
    icon: '/icon-192.png',
    badge: '/icon-192.png',
    // 긴급 알림은 사용자가 직접 닫을 때까지 남긴다.
    requireInteraction: true,
    vibrate: [200, 100, 200],
    // 같은 사건의 알림이 여러 번 와도 하나로 합친다(계속 쌓이면 알림을 꺼 버린다).
    tag: (payload.data && payload.data.case_id) || 'alert',
    renotify: true,
    data: payload.data || {},
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  // 이미 열려 있는 창이 있으면 그 창을 앞으로 — 새 창을 또 열면 로그인 상태가
  // 갈리고 사용자는 "앱이 두 개"로 느낀다.
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((list) => {
      for (const client of list) {
        if ('focus' in client) return client.focus();
      }
      return self.clients.openWindow('/');
    }),
  );
});
