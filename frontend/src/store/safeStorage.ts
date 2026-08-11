/**
 * 저장소가 막혀도 앱은 뜬다.
 *
 * ## 왜 필요한가
 * 웹에서 AsyncStorage 는 `localStorage` 다. 그런데 localStorage 는 **읽기만
 * 해도 예외를 던지는 환경**이 있다.
 *  - 카카오톡·인스타그램 같은 **인앱 브라우저**(WKWebView) 의 비영속 저장소
 *  - 사파리 "모든 쿠키 차단" 설정
 *  - 시크릿 모드 + 용량 초과
 *
 * 세 스토어(auth·guardianCase·engagement)가 모두 zustand `persist` 를 쓰는데,
 * 하이드레이션에서 던진 예외를 아무도 잡지 않으면 **React 가 마운트되기 전에
 * 죽어 흰 화면**이 된다. 화면도 오류도 없이 그냥 비어 있어서, 사용자는 "링크가
 * 안 된다"고만 말할 수 있다(현장 제보 08-11, 카카오톡 인앱 브라우저).
 *
 * ## 무엇을 하나
 * 실패하면 **메모리에 담고 계속 간다.** 앱을 닫으면 로그인은 풀리지만, 그건
 * 아무것도 못 쓰는 것보다 낫다. 한 번 실패하면 다시 시도하지 않는다 — 매
 * 호출마다 예외를 던지는 환경이라 값이 비싸고 로그만 더럽힌다.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

/** 저장소가 죽었을 때 쓰는 대체 보관함. 세션 동안만 산다. */
const fallback = new Map<string, string>();

/** 한 번이라도 던졌으면 이후로는 묻지 않는다. */
let unavailable = false;

function giveUp(where: string, e: unknown): void {
  if (!unavailable) {
    unavailable = true;
    // 조용히 실패하면 나중에 "왜 로그인이 안 풀렸다 붙었다 하지" 를 못 쫓는다.
    console.warn(`[storage] ${where} 실패 — 메모리로 대체합니다.`, e);
  }
}

export const safeStorage = {
  async getItem(key: string): Promise<string | null> {
    if (unavailable) return fallback.get(key) ?? null;
    try {
      return await AsyncStorage.getItem(key);
    } catch (e) {
      giveUp('getItem', e);
      return fallback.get(key) ?? null;
    }
  },

  async setItem(key: string, value: string): Promise<void> {
    // 메모리에는 항상 넣는다 — 디스크가 살아 있어도 같은 세션에서 값이 갈리면 안 된다.
    fallback.set(key, value);
    if (unavailable) return;
    try {
      await AsyncStorage.setItem(key, value);
    } catch (e) {
      giveUp('setItem', e);
    }
  },

  async removeItem(key: string): Promise<void> {
    fallback.delete(key);
    if (unavailable) return;
    try {
      await AsyncStorage.removeItem(key);
    } catch (e) {
      giveUp('removeItem', e);
    }
  },
};
