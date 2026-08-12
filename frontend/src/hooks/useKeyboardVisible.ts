/**
 * 키보드가 떠 있는가 — 하단 탭바를 숨길지 판단하는 데 쓴다.
 *
 * ## 왜 필요한가
 * 웹에서는 키보드가 올라오면 pwa.ts 가 앱 높이를 **보이는 영역**에 맞춰 줄인다.
 * 그래야 입력칸이 키보드 뒤로 숨지 않는다. 그런데 그러면 화면 맨 아래 붙어 있는
 * 하단 탭바까지 함께 올라와 키보드 바로 위에 달라붙는다 — 글자를 칠 때마다
 * 탭이 튀어 오르는 것처럼 보이고(현장 제보 08-12), 안 그래도 좁은 대화 영역을
 * 더 잡아먹는다.
 *
 * 타이핑 중에 탭 이동이 필요한 사람은 없다. 키보드가 있는 동안에는 탭바를
 * 감춘다.
 *
 * ## 웹에서 어떻게 아는가
 * `window.innerHeight`(레이아웃 뷰포트)는 iOS 에서 키보드가 떠도 줄지 않고,
 * `visualViewport.height`(실제로 보이는 영역)만 줄어든다. 그 차이가 키보드
 * 높이다. 임계값을 크게 잡은 이유는 주소창 숨김·툴바 변화처럼 수십 px 짜리
 * 변화를 키보드로 오인하지 않기 위해서다.
 */
import { useEffect, useState } from 'react';
import { Keyboard, Platform } from 'react-native';

/** 이보다 많이 줄었으면 키보드로 본다(px). 브라우저 툴바 변화와 구분하는 선. */
const KEYBOARD_MIN_H = 150;

export function useKeyboardVisible(): boolean {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (Platform.OS !== 'web') {
      const show = Keyboard.addListener('keyboardDidShow', () => setVisible(true));
      const hide = Keyboard.addListener('keyboardDidHide', () => setVisible(false));
      return () => { show.remove(); hide.remove(); };
    }

    const vv = typeof window !== 'undefined' ? window.visualViewport : undefined;
    if (!vv) return;   // 구형 브라우저 — 판정할 수 없으면 숨기지 않는다.

    /**
     * 화면 키보드가 있는 기기인가.
     *
     * 데스크톱에서 입력칸을 눌렀다고 탭바를 감추면 안 된다 — 거기엔 화면
     * 키보드가 없어서 가릴 것도 없다. 터치 기기에서만 포커스로 판단한다.
     */
    const touch = window.matchMedia?.('(pointer: coarse)').matches ?? false;

    const isTextField = (el: Element | null) =>
      el instanceof HTMLElement
      && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable);

    /** 높이 차이로 보는 판정 — 포커스를 놓쳤을 때의 보조 수단. */
    const byHeight = () => window.innerHeight - vv.height > KEYBOARD_MIN_H;

    /**
     * 높이 이벤트가 포커스 판정을 덮어쓰지 않게 한다.
     *
     * 키보드가 올라오는 도중에는 아직 높이 차이가 임계값에 못 미쳐 byHeight()
     * 가 false 다. 그 값을 그대로 쓰면 방금 포커스로 감춘 탭바가 다시 나타났다
     * 사라지며 깜빡인다. 입력칸에 커서가 있는 동안은 무조건 "열림"으로 본다.
     */
    const check = () => {
      if (touch && isTextField(document.activeElement)) { setVisible(true); return; }
      setVisible(byHeight());
    };
    check();

    /**
     * **포커스 순간 바로** 감춘다.
     *
     * 높이 변화만 보면 키보드가 올라오는 ~300ms 동안 탭바가 화면 위로 따라
     * 올라오다가 임계값을 넘겨야 사라진다 — 그 구간이 "탭이 튄다"로 보였다
     * (현장 제보 08-12). 포커스는 그 애니메이션이 시작되기 전에 오므로
     * 올라올 틈이 없다.
     */
    const onFocusIn = (e: FocusEvent) => {
      if (touch && isTextField(e.target as Element)) setVisible(true);
    };
    /** 다른 입력칸으로 옮겨 가는 중일 수 있어 한 프레임 뒤에 확인한다. */
    const onFocusOut = () => {
      requestAnimationFrame(() => {
        if (isTextField(document.activeElement)) return;
        setVisible(byHeight());
      });
    };

    vv.addEventListener('resize', check);
    // 키보드를 올린 채 화면을 밀면 높이는 그대로고 offset 만 변한다. 그 순간에도
    // 판정이 뒤집히지 않도록 같은 함수를 붙여 둔다.
    vv.addEventListener('scroll', check);
    document.addEventListener('focusin', onFocusIn, true);
    document.addEventListener('focusout', onFocusOut, true);
    return () => {
      vv.removeEventListener('resize', check);
      vv.removeEventListener('scroll', check);
      document.removeEventListener('focusin', onFocusIn, true);
      document.removeEventListener('focusout', onFocusOut, true);
    };
  }, []);

  return visible;
}

export default useKeyboardVisible;
