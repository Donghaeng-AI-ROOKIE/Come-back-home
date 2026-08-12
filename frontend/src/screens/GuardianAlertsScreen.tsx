/**
 * 보호자 알림 탭 — 제보 알림 (피그마 2695:15003 목록 / 2696:15126 상세).
 *
 * ## 화면 구조: 위는 확률지도, 아래는 제보 목록
 * 시민 모드의 긴급 알림(AlertSyncScreen)과 **같은 골격**이다 — 지도가 배경으로
 * 깔리고 그 위로 시트가 올라온다. 보호자가 제보 목록만 보고 있으면 "대흥역 4번
 * 출구에서 4건"이 **예상 이동 범위의 어디인지** 알 수 없었다. 제보는 예측을
 * 갱신하는 입력이므로, 둘은 같은 화면에서 붙어 있어야 읽힌다.
 *
 * 시트는 손잡이로 끌어 키우고 줄인다(시민 화면과 동일한 두 자리). 제보가 많으면
 * 시트를 올려 목록을, 위치를 보고 싶으면 내려 지도를 본다.
 *
 * 지도는 **이 기기가 접수한 가장 최근 사건**의 POA 를 그린다. 사건이 없으면
 * (또는 아직 예측 전이면) 지도 없이 목록만 전체 화면으로 — 빈 지도는 정보가
 * 아니라 잡음이다.
 *
 * ## 카드 하나 = 사건이 아니라 **제보가 모인 위치**
 * 시안의 카드 제목이 "[서울시 마포구] 대흥역 4번 출구 근처", 본문이 "해당 위치에서
 * 총 4건의 제보가 있습니다" 다. 보호자가 알고 싶은 건 "어디서 목격됐나"이지 사건
 * 번호가 아니다. 그래서 내 사건의 제보를 **위치(res9 셀)로 묶어** 카드로 만든다.
 *
 * ## 어느 사건을 읽는가
 * 이 기기가 접수한 사건만(store/guardianCaseStore). 활성 경보를 통째로 받아 오면
 * 남의 실종 사건과 제보 원문까지 보호자 화면에 뜬다 — 백엔드가 그 경로를
 * fail-closed 로 막아 둔 이유다(api/phase3.list_active_alerts).
 *
 * ## 시각 표기
 * `seen_at`(목격 시각)은 시민이 입력한 **로컬** 시각, `created_at`(접수 시각)은
 * 서버가 찍은 값인데 배포 컨테이너 시계가 UTC 라 naive UTC 로 온다. 같은 함수로
 * 파싱하면 접수 시각만 9시간 어긋난다 — 08-10 실측(15:42 접수 → 06:42 표시).
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Animated, PanResponder, Platform, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { latLngToCell } from 'h3-js';
import { color, type } from '../theme/tokens';
import FigmaStatusBar from '../components/FigmaStatusBar';
import BaseMap from '../components/BaseMap';
import PoaHeatmap from '../components/PoaHeatmap';
import MapPin from '../components/MapPin';
import WebMap from '../components/WebMap';
import { useAreaLabels, useGuardianCases, usePoaPrediction } from '../hooks/queries';
import type { Case, CaseTip } from '../api/guardian';

/** 제보를 묶는 단위 — 백엔드 예측 격자와 같은 res9(≈한 변 174m, 골목 한 구획). */
const GROUP_RES = 9;
const UNKNOWN = 'unknown';

/**
 * 시트가 멈추는 두 자리 — 시민 긴급 알림(AlertSyncScreen)과 같은 값.
 *
 * 접힘(367)은 지도가 주인공인 자리, 펼침(140)은 상태바와 지도 일부만 남기고
 * 제보 목록을 최대한 보여 주는 자리. 중간에서 손을 떼면 가까운 쪽으로 붙는다.
 */
const SHEET_COLLAPSED_TOP = 367;
const SHEET_EXPANDED_TOP = 140;

type TipGroup = {
  key: string;
  center: { lat: number; lng: number } | null;
  tips: CaseTip[];
  /** 그룹 내 최신 제보 시각(정렬용, epoch ms). */
  latest: number;
};

/** 서버가 찍은 naive UTC 를 UTC 로 해석. 오프셋이 이미 있으면 그대로 둔다. */
function parseServerTime(iso: string): number {
  const hasOffset = iso.endsWith('Z') || iso.includes('+');
  return new Date(hasOffset ? iso : `${iso}Z`).getTime();
}

/** 목격 시각이 있으면 그것을, 없으면 접수 시각을 쓴다(각각 다른 시간대 규칙). */
function tipTime(tip: CaseTip): number {
  if (tip.seen_at) {
    const t = new Date(tip.seen_at).getTime(); // 사용자가 입력한 로컬 naive
    if (!Number.isNaN(t)) return t;
  }
  return parseServerTime(tip.created_at);
}

function timeText(tip: CaseTip): string {
  const t = tipTime(tip);
  if (Number.isNaN(t)) return '';
  const d = new Date(t);
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}/${d.getMonth() + 1}/${d.getDate()} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

/** 그룹 안 최고 신뢰도 → 시안의 배지 문구. p 가 아직 없으면 "검토 중". */
function trustLabel(tips: CaseTip[]): string {
  const scores = tips.map((t) => t.p).filter((p): p is number => typeof p === 'number');
  if (!scores.length) return '검토 중';
  const best = Math.max(...scores);
  return best >= 0.8 ? '신뢰도 상' : best >= 0.5 ? '신뢰도 중' : '신뢰도 하';
}

/** 내 사건들의 제보를 위치로 묶는다. 위치 없는 제보도 버리지 않고 한 묶음으로. */
function groupTips(cases: Case[]): TipGroup[] {
  const map = new Map<string, TipGroup>();
  for (const c of cases) {
    for (const tip of c.tips ?? []) {
      const loc = tip.location ?? null;
      let key = UNKNOWN;
      if (loc && Number.isFinite(loc.lat) && Number.isFinite(loc.lng)) {
        try {
          key = latLngToCell(loc.lat, loc.lng, GROUP_RES);
        } catch {
          key = UNKNOWN;
        }
      }
      const g = map.get(key);
      if (g) {
        g.tips.push(tip);
        g.latest = Math.max(g.latest, tipTime(tip));
      } else {
        map.set(key, {
          key,
          center: key === UNKNOWN ? null : { lat: loc!.lat, lng: loc!.lng },
          tips: [tip],
          latest: tipTime(tip),
        });
      }
    }
  }
  const out = [...map.values()];
  for (const g of out) g.tips.sort((a, b) => tipTime(b) - tipTime(a));
  return out.sort((a, b) => b.latest - a.latest);
}

/** 지도에 그릴 사건 — 최종 목격 좌표가 있는 것 중 가장 최근(스토어가 최신순). */
function mapCaseOf(cases: Case[]): Case | null {
  return cases.find((c) => c.lkp && Number.isFinite(c.lkp.lat) && Number.isFinite(c.lkp.lng)) ?? null;
}

export default function GuardianAlertsScreen() {
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const { data, isLoading, isError, refetch } = useGuardianCases();

  const cases = data ?? [];
  const groups = useMemo(() => groupTips(cases), [data]);
  const centers = useMemo(
    () => groups.map((g) => g.center).filter((c): c is { lat: number; lng: number } => c != null),
    [groups],
  );
  const { data: labels } = useAreaLabels(centers);

  /** 지도는 최근 사건 하나만 그린다 — 여러 사건의 POA 를 겹쳐 놓으면 읽을 수 없다. */
  const mapCase = useMemo(() => mapCaseOf(cases), [data]);
  const poa = usePoaPrediction(mapCase?.id ?? '', 0);
  const lkp = mapCase?.lkp;
  const hasMap = lkp != null;
  const region = lkp ? {
    latitude: lkp.lat,
    longitude: lkp.lng,
    latitudeDelta: 0.012,
    longitudeDelta: 0.012,
  } : undefined;

  /**
   * 제보가 늘면 지도를 다시 읽는다.
   *
   * 제보는 예측을 갱신하는 **입력**이라(백엔드가 tip 반영 후 POA 를 다시 계산한다),
   * 목록만 갱신되고 지도가 그대로면 같은 화면 안에서 두 값이 어긋난다 — 보호자가
   * 이 탭을 열어 둔 채 제보를 기다리는 화면이라 더 그렇다. 사건 목록은
   * useGuardianCases 가 주기적으로 다시 묻고 있으므로, 그 결과의 제보 수가 바뀐
   * 순간만 잡아 한 번 더 읽는다(주기 폴링을 하나 더 만들지 않는다).
   */
  const tipCount = useMemo(() => cases.reduce((n, c) => n + (c.tips?.length ?? 0), 0), [data]);
  const refetchPoa = poa.refetch;
  useEffect(() => {
    if (mapCase == null) return;
    refetchPoa();
  }, [tipCount, mapCase?.id, refetchPoa]);

  /** 그룹 → 표시 이름. 이름이 아직 안 왔으면 좌표로 버틴다(빈 카드보다 낫다). */
  const nameOf = (g: TipGroup): string => {
    if (g.center == null) return '위치 정보 없는 제보';
    const idx = centers.indexOf(g.center);
    return labels?.[idx] ?? `${g.center.lat.toFixed(4)}, ${g.center.lng.toFixed(4)}`;
  };

  const selected = groups.find((g) => g.key === selectedKey) ?? null;
  const hasCase = cases.length > 0;

  /**
   * 손잡이를 끌어 시트를 키우고 줄인다(시민 AlertSyncScreen 과 같은 동작).
   *
   * 제스처를 **손잡이 영역에만** 건다 — 시트 전체에 걸면 안쪽 목록을 넘기려는
   * 손짓과 다툰다. `top` 은 레이아웃 값이라 네이티브 드라이버를 쓸 수 없다.
   */
  const sheetTop = useRef(new Animated.Value(SHEET_COLLAPSED_TOP)).current;
  const liveTop = useRef(SHEET_COLLAPSED_TOP);
  const grabbedAt = useRef(SHEET_COLLAPSED_TOP);
  useEffect(() => {
    const id = sheetTop.addListener(({ value }) => { liveTop.current = value; });
    return () => sheetTop.removeListener(id);
  }, [sheetTop]);

  const snapTo = (to: number) => {
    Animated.timing(sheetTop, { toValue: to, duration: 180, useNativeDriver: false }).start();
  };

  const pan = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: (_e, g) => Math.abs(g.dy) > 2,
      onPanResponderGrant: () => { grabbedAt.current = liveTop.current; },
      onPanResponderMove: (_e, g) => {
        const next = Math.min(SHEET_COLLAPSED_TOP, Math.max(SHEET_EXPANDED_TOP, grabbedAt.current + g.dy));
        sheetTop.setValue(next);
      },
      onPanResponderRelease: (_e, g) => {
        const mid = (SHEET_COLLAPSED_TOP + SHEET_EXPANDED_TOP) / 2;
        const snap = (to: number) =>
          Animated.timing(sheetTop, { toValue: to, duration: 180, useNativeDriver: false }).start();
        // 거의 안 움직였으면 탭으로 보고 반대쪽으로 넘긴다.
        if (Math.abs(g.dy) < 4) {
          snap(grabbedAt.current > mid ? SHEET_EXPANDED_TOP : SHEET_COLLAPSED_TOP);
          return;
        }
        // 빠르게 튕기면 손이 간 방향을, 천천히 놓으면 가까운 쪽을 따른다.
        if (g.vy > 0.5) snap(SHEET_COLLAPSED_TOP);
        else if (g.vy < -0.5) snap(SHEET_EXPANDED_TOP);
        else snap(grabbedAt.current + g.dy < mid ? SHEET_EXPANDED_TOP : SHEET_COLLAPSED_TOP);
      },
    }),
  ).current;

  /** 상세로 들어가면 시트를 올린다 — 제보 원문은 읽으라고 여는 것이다. */
  const openGroup = (key: string) => {
    setSelectedKey(key);
    if (hasMap) snapTo(SHEET_EXPANDED_TOP);
  };
  const closeGroup = () => {
    setSelectedKey(null);
    if (hasMap) snapTo(SHEET_COLLAPSED_TOP);
  };

  return (
    <View style={styles.root}>
      {/* 지도 — 시민 화면과 같은 규칙. 웹은 react-native-maps 가 없어 실제 OSM
          타일 + 서버가 준 실제 POA 셀을 직접 그린다(components/WebMap). */}
      {lkp ? (
        Platform.OS === 'web' ? (
          <WebMap
            style={styles.map}
            center={lkp}
            marker={lkp}
            grid={poa.data}
            accessibilityLabel="실제 발견확률 지도"
          />
        ) : (
          <BaseMap
            style={styles.map}
            region={region}
            accessibilityLabel={poa.data ? `실제 발견확률 지도. ${poa.data.topLabel}` : '발견확률 지도를 불러오는 중'}
          >
            {poa.data ? <PoaHeatmap grid={poa.data} /> : null}
            <MapPin kind="lastSeen" coordinate={lkp} title="최종 목격 위치" />
          </BaseMap>
        )
      ) : null}
      {hasMap && poa.isLoading && Platform.OS !== 'web' ? (
        <ActivityIndicator style={styles.mapLoading} color={color.guardian} />
      ) : null}
      {/* 지도가 있으면 시계는 지도 위에 뜬다(시민 화면과 같다). 지도가 없을 때는
          시트가 화면 전체라, 같은 자리에 띄우면 "제보 알림" 제목과 겹친다 —
          그때는 아래에서 흐름 배치로 자리를 차지하게 둔다. */}
      {lkp ? <View style={styles.status}><FigmaStatusBar /></View> : null}

      {/* 시트 — 사건이 없으면 지도가 없으므로 화면을 통째로 쓴다.
          내용은 흐름 배치로 스크롤에 맡긴다(절대좌표로는 시트 높이가 바뀔 때
          내용 높이를 알 수 없어 스크롤 자체가 성립하지 않는다). */}
      <Animated.View
        style={[
          styles.sheet,
          hasMap ? styles.sheetOverMap : styles.sheetFull,
          hasMap ? { top: sheetTop } : null,
        ]}
      >
        {hasMap ? (
          <View
            style={styles.grip}
            {...pan.panHandlers}
            accessibilityRole="adjustable"
            accessibilityLabel="제보 목록 카드 크기 조절"
          >
            <View style={styles.handle} />
          </View>
        ) : (
          <FigmaStatusBar />
        )}

        {selected == null ? (
          <ScrollView contentContainerStyle={[styles.sheetBody, hasMap ? null : styles.sheetBodyFull]} showsVerticalScrollIndicator={false}>
            <Text style={styles.title}>제보 알림</Text>
            <Text style={styles.subtitle}>주변 시민들의 실제 제보입니다.</Text>
            {isLoading ? <ActivityIndicator color={color.guardian} style={styles.loading} /> : null}
            {isError ? (
              <Pressable style={styles.empty} onPress={() => refetch()}>
                <Text style={styles.emptyText}>제보를 불러오지 못했습니다.{`\n`}눌러서 다시 시도해 주세요.</Text>
              </Pressable>
            ) : null}
            {!isLoading && !isError && groups.length === 0 ? (
              <View style={styles.empty}>
                <Text style={styles.emptyText}>
                  {hasCase
                    ? '아직 접수된 시민 제보가 없습니다.\n제보가 들어오면 이곳에 바로 표시됩니다.'
                    : '진행 중인 실종 신고가 없습니다.'}
                </Text>
              </View>
            ) : null}
            {groups.map((g, index) => (
              <Pressable
                key={g.key}
                style={[styles.alertCard, index === 0 ? styles.firstCard : null]}
                onPress={() => openGroup(g.key)}
                accessibilityRole="button"
                accessibilityLabel={`${nameOf(g)}, 제보 ${g.tips.length}건, ${trustLabel(g.tips)}`}
              >
                <View style={styles.trust}><Text style={styles.trustText}>{trustLabel(g.tips)}</Text></View>
                <Text style={styles.cardTitle} numberOfLines={1}>{nameOf(g)}</Text>
                <Text style={styles.cardBody}>해당 위치에서 총 {g.tips.length}건의 제보가 있습니다.</Text>
                <Text style={styles.chevron}>›</Text>
              </Pressable>
            ))}
          </ScrollView>
        ) : (
          <ScrollView contentContainerStyle={[styles.sheetBody, hasMap ? null : styles.sheetBodyFull]} showsVerticalScrollIndicator={false}>
            <View style={styles.header}>
              <Pressable style={styles.back} onPress={closeGroup} accessibilityRole="button" accessibilityLabel="목록으로">
                <Text style={styles.backText}>‹</Text>
              </Pressable>
              <Text style={styles.headerTitle}>상세 제보</Text>
            </View>
            <View style={styles.locationCard}>
              <Text style={styles.locationText} numberOfLines={2}>{nameOf(selected)}</Text>
            </View>
            <Text style={styles.reportCount}>제보 {selected.tips.length}건</Text>
            {selected.tips.map((tip) => (
              <View key={tip.id} style={styles.reportCard}>
                <Text style={styles.reportDate}>{timeText(tip)}</Text>
                <Text style={styles.reportText} numberOfLines={2}>{tip.text}</Text>
              </View>
            ))}
          </ScrollView>
        )}
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#FFFFFF', overflow: 'hidden' },
  map: { position: 'absolute', left: 0, right: 0, top: 0, width: '100%', height: 383 },
  mapLoading: { position: 'absolute', top: 170, left: 0, right: 0 },
  status: { position: 'absolute', top: 0, left: 0, right: 0 },
  sheet: { position: 'absolute', left: 0, right: 0, bottom: 0, backgroundColor: '#FFFFFF' },
  sheetOverMap: {
    borderTopLeftRadius: 12,
    borderTopRightRadius: 12,
    backgroundColor: 'rgba(255,255,255,0.96)',
    shadowColor: '#000',
    shadowOpacity: 0.14,
    shadowRadius: 25,
    shadowOffset: { width: 0, height: -2 },
    elevation: 8,
  },
  sheetFull: { top: 0 },
  // 손잡이는 얇지만 잡는 영역은 넉넉해야 한다 — 5px 막대만 노리게 하면 안 잡힌다.
  grip: { paddingTop: 8, paddingBottom: 8, alignItems: 'center' },
  handle: { width: 40, height: 5, borderRadius: 3, backgroundColor: 'rgba(0,0,0,0.1)' },
  sheetBody: { paddingTop: 14, paddingBottom: 18 },
  /** 지도 없이 화면 전체를 쓸 때는 시안의 제목 위치(상태바 아래 27)를 그대로 지킨다. */
  sheetBodyFull: { paddingTop: 27 },
  title: { marginLeft: 20, fontFamily: type.familyCssBold, fontSize: 18, lineHeight: 23, color: '#000000' },
  subtitle: { marginLeft: 20, marginTop: 9, fontFamily: type.familyCssBold, fontSize: 11, lineHeight: 13, color: '#8E8E93' },
  loading: { marginTop: 30 },
  empty: { marginLeft: 23, marginRight: 22, marginTop: 20, minHeight: 100, borderRadius: 10, backgroundColor: '#F7F7F7', alignItems: 'center', justifyContent: 'center', padding: 16 },
  emptyText: { fontFamily: type.familyCssBold, fontSize: 12, lineHeight: 18, color: '#8E8E93', textAlign: 'center' },
  // 카드 간격은 시안(28)보다 좁은 14 — 시트가 화면의 절반이라 시안 간격 그대로면
  // 접힌 상태에서 카드 한 장 반밖에 안 보인다.
  firstCard: { marginTop: 22 },
  alertCard: { marginLeft: 23, marginRight: 22, marginTop: 14, height: 115, borderRadius: 10, backgroundColor: '#F7F7F7', shadowColor: '#000', shadowOpacity: 0.1, shadowRadius: 10, shadowOffset: { width: 1, height: 1 } },
  trust: { position: 'absolute', left: 16, top: 15, height: 16, minWidth: 59, paddingHorizontal: 10, borderRadius: 20, backgroundColor: '#B0DB9C', alignItems: 'center', justifyContent: 'center' },
  trustText: { fontFamily: type.familyCssBold, fontSize: 10, lineHeight: 13, color: '#316837' },
  cardTitle: { position: 'absolute', left: 16, right: 28, top: 41, fontFamily: type.familyCssBold, fontSize: 17, lineHeight: 22, color: '#525253' },
  cardBody: { position: 'absolute', left: 16, top: 70, fontFamily: type.familyCssBold, fontSize: 11, lineHeight: 13, color: '#525253' },
  chevron: { position: 'absolute', right: 14, top: 19, fontSize: 24, color: '#67AE6E' },
  header: { height: 32, justifyContent: 'center', alignItems: 'center' },
  headerTitle: { fontFamily: type.familyCssBold, fontSize: 18, lineHeight: 23, color: '#000000' },
  back: { position: 'absolute', left: 12, top: 2, width: 24, height: 28, justifyContent: 'center' },
  backText: { fontSize: 34, lineHeight: 28, color: '#8E8E93', fontWeight: '300' },
  locationCard: { marginLeft: 23, marginRight: 22, marginTop: 11, minHeight: 51, borderRadius: 10, backgroundColor: '#F7F7F7', justifyContent: 'center', paddingHorizontal: 16, paddingVertical: 10 },
  locationText: { fontFamily: type.familyCssBold, fontSize: 15, lineHeight: 19, color: '#525253' },
  reportCount: { marginLeft: 26, marginTop: 21, fontFamily: type.familyCssBold, fontSize: 11, lineHeight: 13, color: '#525253' },
  reportCard: { marginLeft: 23, marginRight: 22, marginTop: 12, height: 66, borderRadius: 8, backgroundColor: '#F8F8F8', paddingHorizontal: 16, paddingTop: 12 },
  reportDate: { fontFamily: type.familyCssBold, fontSize: 11, lineHeight: 13, color: '#4D4D4D' },
  reportText: { fontFamily: type.familyCssBold, fontSize: 11, lineHeight: 13, color: '#4D4D4D', marginTop: 9 },
});
