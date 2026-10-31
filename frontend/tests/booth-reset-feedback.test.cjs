// 실제 부스 버튼 핸들러와 notify.ts를 웹 환경에서 실행한다.
// 서버/API는 대역이며 네트워크·가족 삭제·신고 종료는 발생하지 않는다.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');

function load(file, modules = {}, globals = {}) {
  const source = ts.transpileModule(fs.readFileSync(path.join(__dirname, '..', file), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.React },
  }).outputText;
  const out = { exports: {} };
  vm.runInNewContext(source, {
    module: out, exports: out.exports, console, ...globals,
    require: (name) => {
      assert.ok(Object.hasOwn(modules, name), `unexpected import: ${name}`);
      return modules[name];
    },
  });
  return out.exports;
}

const { ApiError } = load('src/api/errors.ts');
const clone = (value) => value === undefined ? undefined : JSON.parse(JSON.stringify(value));
const saved = { exists: true, name: '검증 가족', age: '78세', n_messages: 8 };

function mount(options = {}) {
  const calls = { refetch: [], confirm: [], prepare: [], capture: [], prepared: [], reset: 0, removed: [], nav: [], alert: [], nativeAlert: [] };
  const existingFamily = { id: 'existing-persona', name: '기존 가족', age: 78 };
  const cache = new Map([
    ['personas', [existingFamily]], ['personaStatus', { persona_status: 'complete' }],
    ['guardianCases', [{ id: 'existing-case', status: 'searching' }]],
  ]);
  const guardian = { persona: existingFamily, reset: () => { calls.reset++; guardian.persona = null; } };
  const slots = [];
  let cursor = 0;
  let pressables = [];
  const hooks = {
    ...React,
    useState: (initial) => {
      const index = cursor++;
      if (!(index in slots)) slots[index] = typeof initial === 'function' ? initial() : initial;
      return [slots[index], (value) => { slots[index] = typeof value === 'function' ? value(slots[index]) : value; }];
    },
  };
  const Box = ({ children }) => React.createElement('div', null, children);
  const Text = ({ children, accessibilityRole }) => React.createElement('span', { role: accessibilityRole }, children);
  const Pressable = (props) => {
    pressables.push(props);
    return React.createElement('button', { disabled: !!props.disabled, 'aria-label': props.accessibilityLabel }, props.children);
  };
  const native = {
    View: Box, ScrollView: Box, Text, Pressable, ActivityIndicator: () => null,
    StyleSheet: { create: (value) => value }, Platform: { OS: 'web' },
    Alert: { alert: (...args) => calls.nativeAlert.push(args) },
  };
  const window = {
    alert: (message) => calls.alert.push(message),
    confirm: (message) => { calls.confirm.push(message); return options.confirm !== false; },
  };
  const tokens = { color: {}, radius: {}, space: {}, type: { size: {} } };
  const cta = load('src/components/CTAButton.tsx', { react: React, 'react-native': native, '../theme/tokens': tokens });
  // notify 대역으로 성공을 꾸미지 않는다. 실제 웹 window.alert 경로를 확인한다.
  const notify = load('src/utils/notify.ts', { 'react-native': native }, { window });
  const booth = {
    data: options.cached ?? saved,
    refetch: async (config) => {
      calls.refetch.push(clone(config));
      if (options.refetchError) throw options.refetchError;
      return { data: options.latest ?? saved };
    },
  };
  const screenComponents = {};
  const Screen = ({ name, component }) => { screenComponents[name] = component; return null; };
  const noopScreen = { __esModule: true, default: () => null };
  const modules = {
    react: hooks, 'react-native': native,
    '@react-navigation/native': { useNavigation: () => ({ navigate: (...args) => calls.nav.push(clone(args)) }) },
    '@react-navigation/bottom-tabs': { createBottomTabNavigator: () => ({ Navigator: Box, Screen }) },
    '@react-navigation/elements': { PlatformPressable: Pressable },
    '@tanstack/react-query': { useQueryClient: () => ({ removeQueries: (query) => { calls.removed.push(clone(query)); cache.delete(query.queryKey[0]); } }) },
    'react-native-safe-area-context': { SafeAreaView: Box },
    '../api/guardian': {
      captureDemoTemplate: async (...args) => {
        calls.capture.push(args);
        if (options.captureError) throw options.captureError;
        return saved;
      },
      captureDemoPrepared: async (...args) => {
        calls.prepared.push(args);
        if (options.preparedError) throw options.preparedError;
        return { ...saved, prepared: { exists: true, n_rules: 3, prepared_at: '2026-10-31T13:31:36' } };
      },
      prepareNextDemoTurn: async (...args) => {
        calls.prepare.push(args);
        if (options.prepareError) throw options.prepareError;
        return options.prepareResult ?? { session: { id: 'new-session' } };
      },
    },
    '../api/config': { ApiError }, '../theme/tokens': tokens,
    '../theme/tabBar': { useTabBarMetrics: () => ({ height: 80, paddingBottom: 8, showFakeIndicator: false }) },
    '../hooks/useKeyboardVisible': { useKeyboardVisible: () => false },
    '../components/CTAButton': cta,
    '../screens/GuardianHomeScreen': noopScreen, '../screens/RegChatScreen': noopScreen,
    '../screens/GuardianAlertsScreen': noopScreen, '../components/FigmaTabIcon': noopScreen,
    '../store/authStore': { useAuthStore: () => ({ user: '검증 계정', userId: 'test-user', signOut() {}, switchRole() {} }) },
    '../store/guardianStore': { useGuardianStore: (selector) => selector(guardian) },
    '../store/guardianCaseStore': { useGuardianCaseStore: (selector) => selector({ markTipsSeen() {} }) },
    '../hooks/queries': {
      useDemoBooth: () => booth,
      usePersonas: () => ({ data: cache.get('personas'), isLoading: false }),
      useGuardianCases: () => ({ data: [] }),
    },
    '../utils/guardianTips': { listedCases: (cases) => cases },
    '../utils/guardianSearchCard': { activeCases: (cases) => cases },
    '../utils/tabAccent': { guardianEmergency: () => false, guardianTabAccent: () => 'guardian' },
    '../utils/notify': notify,
  };
  const tabs = load('src/navigation/GuardianTabs.tsx', modules, { window });
  // 비공개 화면을 소스 문자열로 뜯지 않고 실제 탭 등록의 component를 가져온다.
  renderToStaticMarkup(React.createElement(tabs.default));
  assert.equal(typeof screenComponents.GuardianMy, 'function');
  const render = () => {
    cursor = 0;
    pressables = [];
    return renderToStaticMarkup(React.createElement(screenComponents.GuardianMy));
  };
  const button = (label) => {
    const hit = pressables.find((props) => props.accessibilityLabel === label);
    assert.ok(hit, `missing button: ${label}`);
    return hit;
  };
  const press = (label) => {
    const hit = button(label);
    assert.equal(!!hit.disabled, false, `${label} must be enabled before pressing`);
    return hit.onPress();
  };
  const unchanged = () => {
    assert.equal(calls.reset, 0);
    assert.deepEqual(calls.removed, []);
    assert.deepEqual(calls.nav, []);
    assert.equal(guardian.persona, existingFamily);
    assert.equal(cache.size, 3, 'family/status/case cache must survive a failed or cancelled operation');
    assert.equal(cache.get('personas')[0], existingFamily);
  };
  const feedback = (message) => {
    assert.equal(calls.alert.length, 1, 'actual notify must reach window.alert');
    assert.match(calls.alert[0], message);
    assert.deepEqual(calls.nativeAlert, [], 'web feedback must not use the unimplemented native Alert');
    const html = render();
    assert.match(html, /role="alert"/);
    assert.match(html, message);
  };
  render();
  return { calls, cache, guardian, render, button, press, unchanged, feedback };
}

test('latest template absence overrides stale cache and prevents confirmation, deletion and navigation', async () => {
  const ui = mount({ cached: saved, latest: { exists: false } });
  await ui.press('다음 체험 준비');
  assert.deepEqual(ui.calls.refetch, [{ throwOnError: true }]);
  assert.deepEqual(ui.calls.confirm, []);
  assert.deepEqual(ui.calls.prepare, []);
  ui.unchanged();
  ui.feedback(/먼저 시작 대화를 저장해 주세요/);
  assert.match(ui.calls.alert[0], /기존 가족과 신고는 그대로 유지/);
  assert.equal(ui.button('다음 체험 준비').accessibilityState.disabled, false);
});

test('prepare failure preserves existing family and query caches, reports on web, and releases busy state', async () => {
  const ui = mount({ prepareError: new ApiError(409, '/demo/onboarding/next', '템플릿을 먼저 저장해 주세요') });
  const pending = ui.press('다음 체험 준비');
  ui.render();
  assert.equal(ui.button('준비 중…').accessibilityState.disabled, true);
  await pending;
  assert.equal(ui.calls.confirm.length, 1);
  assert.deepEqual(ui.calls.prepare, [['보호자', 'test-user']]);
  ui.unchanged();
  ui.feedback(/준비하지 못했습니다\n+템플릿을 먼저 저장해 주세요/);
  assert.equal(ui.button('다음 체험 준비').accessibilityState.disabled, false);
});

test('successful preparation clears old caches only after the API succeeds and opens the returned session', async () => {
  let resolvePreparation;
  const result = new Promise((resolve) => { resolvePreparation = resolve; });
  const ui = mount({ cached: { exists: false }, latest: saved, prepareResult: result });
  const pending = ui.press('다음 체험 준비');
  // refetch and confirm both yield; let the actual handler reach its pending API request.
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(ui.calls.prepare.length, 1);
  ui.unchanged();
  resolvePreparation({ session: { id: 'fresh-from-api' } });
  await pending;
  assert.equal(ui.calls.reset, 1);
  assert.deepEqual(ui.calls.removed, [
    { queryKey: ['personas'] }, { queryKey: ['personaStatus'] }, { queryKey: ['guardianCases'] },
  ]);
  assert.equal(ui.cache.size, 0);
  assert.deepEqual(ui.calls.nav, [['RegChat', { sessionId: 'fresh-from-api' }]]);
  ui.render();
  assert.equal(ui.button('다음 체험 준비').accessibilityState.disabled, false);
});

test('template refetch failure stops before confirmation or prepare API and remains visible', async () => {
  const ui = mount({ refetchError: new ApiError(503, '/demo/onboarding/template', '연결을 확인해 주세요') });
  await ui.press('다음 체험 준비');
  assert.deepEqual(ui.calls.confirm, []);
  assert.deepEqual(ui.calls.prepare, []);
  ui.unchanged();
  ui.feedback(/준비하지 못했습니다/);
  assert.match(ui.calls.alert[0], /연결을 확인해 주세요/);
  assert.equal(ui.button('다음 체험 준비').accessibilityState.disabled, false);
});

test('cancelling confirmation does not call prepare or change existing data', async () => {
  const ui = mount({ confirm: false });
  await ui.press('다음 체험 준비');
  assert.equal(ui.calls.refetch.length, 1);
  assert.equal(ui.calls.confirm.length, 1);
  assert.deepEqual(ui.calls.prepare, []);
  assert.deepEqual(ui.calls.alert, []);
  ui.unchanged();
  ui.render();
  assert.equal(ui.button('다음 체험 준비').accessibilityState.disabled, false);
});

test('template capture success refreshes status and shows real web and inline feedback', async () => {
  const ui = mount();
  await ui.press('지금 대화를 템플릿으로 저장');
  assert.deepEqual(ui.calls.capture, [['부스', 'test-user']]);
  assert.equal(ui.calls.refetch.length, 1);
  ui.unchanged();
  ui.feedback(/저장했습니다/);
  assert.match(ui.calls.alert[0], /검증 가족 \(78세\) · 대화 8줄/);
  assert.doesNotMatch(ui.calls.alert[0], /세세/);
  assert.equal(ui.button('지금 대화를 템플릿으로 저장').accessibilityState.disabled, false);
});

test('template capture failure reports the server message on web and releases busy state', async () => {
  const ui = mount({ captureError: new ApiError(409, '/demo/onboarding/template', '요약 확인 단계가 아닙니다') });
  await ui.press('지금 대화를 템플릿으로 저장');
  assert.equal(ui.calls.capture.length, 1);
  assert.deepEqual(ui.calls.refetch, []);
  ui.unchanged();
  ui.feedback(/저장하지 못했습니다/);
  assert.match(ui.calls.alert[0], /요약 확인 단계가 아닙니다/);
  assert.equal(ui.button('지금 대화를 템플릿으로 저장').accessibilityState.disabled, false);
});

test('prepared-result capture saves the latest preparation for the next visitors without touching family data', async () => {
  const ui = mount();
  await ui.press('지금 준비 결과를 템플릿에 저장');
  assert.equal(ui.calls.confirm.length, 1);
  assert.match(ui.calls.confirm[0], /다음 체험자들이 그대로 받도록/);
  assert.deepEqual(ui.calls.prepared, [['test-user']]);
  assert.equal(ui.calls.refetch.length, 1);
  ui.unchanged();
  ui.feedback(/저장했습니다\n+준비 결과: 규칙 3개/);
  assert.equal(ui.button('지금 준비 결과를 템플릿에 저장').accessibilityState.disabled, false);
});

test('prepared-result capture failure shows why (preparation still running) and releases busy state', async () => {
  const ui = mount({ preparedError: new ApiError(409, '/demo/onboarding/template/prepared', '조건부 규칙 준비가 아직 끝나지 않았습니다') });
  await ui.press('지금 준비 결과를 템플릿에 저장');
  assert.equal(ui.calls.prepared.length, 1);
  assert.deepEqual(ui.calls.refetch, []);
  ui.unchanged();
  ui.feedback(/저장하지 못했습니다\n+조건부 규칙 준비가 아직 끝나지 않았습니다/);
  assert.equal(ui.button('지금 준비 결과를 템플릿에 저장').accessibilityState.disabled, false);
});

test('cancelling the prepared-result confirmation calls nothing', async () => {
  const ui = mount({ confirm: false });
  await ui.press('지금 준비 결과를 템플릿에 저장');
  assert.deepEqual(ui.calls.prepared, []);
  assert.deepEqual(ui.calls.alert, []);
  ui.unchanged();
});

test('booth card says whether a prepared result is stored', () => {
  const withPrepared = mount({ cached: { ...saved, prepared: { exists: true, n_rules: 2, prepared_at: '2026-10-31T13:31:36.201734' } } });
  assert.match(withPrepared.render(), /준비 결과: 규칙 2개 · 13:31 계산분 저장됨/);
  const without = mount({ cached: { ...saved, prepared: { exists: false } } });
  assert.match(without.render(), /준비 결과 없음/);
  const noTemplate = mount({ cached: { exists: false } });
  assert.doesNotMatch(noTemplate.render(), /준비 결과:|준비 결과 없음/);
});
