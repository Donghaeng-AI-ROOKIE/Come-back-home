/**
 * 부팅 감시기를 dist/index.html 에 심는다 — 흰 화면을 자기 진단으로 바꾼다.
 *
 * ## 왜 index.html 인가
 * 앱 코드(App.tsx) 안에서는 **번들이 실행되기 전에 죽는 경우**를 잡을 수 없다.
 * 저장소 접근 실패처럼 모듈 최상단에서 던지는 예외가 그렇다. 그러면 화면은
 * 완전히 비고 오류도 안 보인다 — 사용자는 "링크가 안 된다"고만 말할 수 있고,
 * 우리는 그 폰을 손에 쥘 수 없으니 원인을 영영 못 찾는다(현장 08-11, 카카오톡
 * 인앱 브라우저에서 흰 화면).
 *
 * 그래서 번들보다 먼저 도는 인라인 스크립트가 필요하다. Expo 는 index.html 을
 * 자동 생성하므로 소스에 태그를 넣을 자리가 없다 — 내보낸 뒤에 심는다.
 *
 * ## 무엇을 하나
 * 1. 오류를 서버에 남긴다 — `GET /__boot?...` 한 방. nginx 접근 로그에 찍히므로
 *    사용자가 아무것도 옮겨 적지 않아도 우리가 읽을 수 있다.
 * 2. 9초 뒤에도 화면이 비어 있으면 **원인을 화면에 띄우고** 저장 데이터를 지우고
 *    다시 열 수 있는 버튼을 준다.
 *
 * 실행: npm run build:web (expo export 뒤 자동으로 돈다)
 */
import { readFile, writeFile } from 'node:fs/promises';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const target = resolve(here, '..', 'dist', 'index.html');

const MARK = '<!-- boot-guard -->';

const GUARD = `${MARK}
    <script>
    (function () {
      var told = false;
      function tell(kind, msg) {
        if (told) return; told = true;
        try {
          new Image().src = '/__boot?k=' + encodeURIComponent(kind)
            + '&m=' + encodeURIComponent(String(msg).slice(0, 300));
        } catch (e) {}
      }
      function why() {
        var out = [];
        try { localStorage.setItem('__t', '1'); localStorage.removeItem('__t'); out.push('storage=ok'); }
        catch (e) { out.push('storage=FAIL:' + (e && e.name)); }
        out.push('sw=' + ('serviceWorker' in navigator));
        out.push('size=' + window.innerWidth + 'x' + window.innerHeight);
        return out.join(' ');
      }
      function show(head, body) {
        var r = document.getElementById('root');
        if (!r) return;
        r.innerHTML =
          '<div style="padding:28px 22px;font:15px/1.6 -apple-system,BlinkMacSystemFont,sans-serif;color:#222">'
          + '<div style="font-size:18px;font-weight:700;margin-bottom:8px">앱을 열지 못했습니다</div>'
          + '<div style="color:#666;margin-bottom:16px">' + head + '</div>'
          + '<pre style="white-space:pre-wrap;word-break:break-all;background:#F5F5F5;padding:12px;'
          + 'border-radius:8px;font-size:12px;color:#444;margin:0 0 18px">' + body + '</pre>'
          + '<button id="__bg_reset" style="width:100%;padding:14px;border:0;border-radius:10px;'
          + 'background:#328E6E;color:#fff;font-size:16px;font-weight:600">저장된 데이터 지우고 다시 열기</button>'
          + '<div style="margin-top:14px;color:#8E8E93;font-size:13px">'
          + '카카오톡·인스타그램 안에서 열었다면, 오른쪽 아래 공유 버튼으로 <b>사파리에서 열기</b>를 눌러 주세요.</div>'
          + '</div>';
        var b = document.getElementById('__bg_reset');
        if (b) b.onclick = function () {
          try { localStorage.clear(); } catch (e) {}
          try { sessionStorage.clear(); } catch (e) {}
          location.replace('/');
        };
      }
      // 리소스 로드 실패(이미지 404 등)는 여기로 안 온다 — capture 를 안 걸었다.
      window.addEventListener('error', function (e) {
        var m = (e.message || 'error') + ' @ '
          + String(e.filename || '').split('/').pop() + ':' + (e.lineno || 0);
        tell('error', m);
        show('실행 중 오류가 났습니다.', m + '\\n' + why());
      });
      window.addEventListener('unhandledrejection', function (e) {
        var r = e.reason;
        tell('reject', (r && (r.message || r)) || 'unknown');
      });
      // 오류 없이 조용히 비어 있는 경우 — 이쪽이 더 흔하다.
      setTimeout(function () {
        var r = document.getElementById('root');
        if (r && r.children.length === 0) {
          var w = why();
          tell('blank', w);
          show('화면이 비어 있습니다.', w);
        }
      }, 9000);
    })();
    </script>`;

const html = await readFile(target, 'utf8');

if (html.includes(MARK)) {
  console.log('[boot-guard] 이미 심어져 있습니다 — 건너뜁니다.');
  process.exit(0);
}
if (!html.includes('</head>')) {
  console.error('[boot-guard] </head> 를 찾지 못했습니다. index.html 구조가 바뀌었습니다.');
  process.exit(1);
}

await writeFile(target, html.replace('</head>', `${GUARD}\n  </head>`), 'utf8');
console.log('[boot-guard] dist/index.html 에 심었습니다.');
