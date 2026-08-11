/**
 * 보호자 알림 탭 — 제보 알림 (피그마 2695:15003 목록 / 2696:15126 상세).
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
import { useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { latLngToCell } from 'h3-js';
import { color, type } from '../theme/tokens';
import FigmaStatusBar from '../components/FigmaStatusBar';
import { useAreaLabels, useGuardianCases } from '../hooks/queries';
import type { Case, CaseTip } from '../api/guardian';

/** 제보를 묶는 단위 — 백엔드 예측 격자와 같은 res9(≈한 변 174m, 골목 한 구획). */
const GROUP_RES = 9;
const UNKNOWN = 'unknown';

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

export default function GuardianAlertsScreen() {
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const { data, isLoading, isError, refetch } = useGuardianCases();

  const groups = useMemo(() => groupTips(data ?? []), [data]);
  const centers = useMemo(
    () => groups.map((g) => g.center).filter((c): c is { lat: number; lng: number } => c != null),
    [groups],
  );
  const { data: labels } = useAreaLabels(centers);

  /** 그룹 → 표시 이름. 이름이 아직 안 왔으면 좌표로 버틴다(빈 카드보다 낫다). */
  const nameOf = (g: TipGroup): string => {
    if (g.center == null) return '위치 정보 없는 제보';
    const idx = centers.indexOf(g.center);
    return labels?.[idx] ?? `${g.center.lat.toFixed(4)}, ${g.center.lng.toFixed(4)}`;
  };

  const selected = groups.find((g) => g.key === selectedKey) ?? null;
  const hasCase = (data ?? []).length > 0;

  return (
    <View style={styles.root}>
      <FigmaStatusBar />
      <View style={styles.canvas}>
        {selected == null ? (
          <>
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
            {/* 카드는 시안 그대로 절대 위치. 개수가 늘면 화면을 넘으므로 스크롤로 감싼다. */}
            <ScrollView
              style={styles.scroll}
              contentContainerStyle={{ height: Math.max(0, 115 + groups.length * 143) }}
              showsVerticalScrollIndicator={false}
            >
              {groups.map((g, index) => (
                <Pressable
                  key={g.key}
                  style={[styles.alertCard, { top: 115 + index * 143 }]}
                  onPress={() => setSelectedKey(g.key)}
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
          </>
        ) : (
          <>
            <View style={styles.header}>
              <Pressable style={styles.back} onPress={() => setSelectedKey(null)} accessibilityRole="button" accessibilityLabel="목록으로">
                <Text style={styles.backText}>‹</Text>
              </Pressable>
              <Text style={styles.headerTitle}>상세 제보</Text>
            </View>
            <View style={styles.locationCard}>
              <Text style={styles.locationText} numberOfLines={2}>{nameOf(selected)}</Text>
            </View>
            <Text style={styles.reportCount}>제보 {selected.tips.length}건</Text>
            <ScrollView
              style={styles.scroll}
              contentContainerStyle={{ height: Math.max(0, 158 + selected.tips.length * 81) }}
              showsVerticalScrollIndicator={false}
            >
              {selected.tips.map((tip, index) => (
                <View key={tip.id} style={[styles.reportCard, { top: 158 + index * 81 }]}>
                  <Text style={styles.reportDate}>{timeText(tip)}</Text>
                  <Text style={styles.reportText} numberOfLines={2}>{tip.text}</Text>
                </View>
              ))}
            </ScrollView>
          </>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#FFFFFF' },
  canvas: { flex: 1, position: 'relative' },
  scroll: { position: 'absolute', left: 0, right: 0, top: 0, bottom: 0 },
  title: { position: 'absolute', left: 20, top: 27, fontFamily: type.familyBold, fontSize: 18, lineHeight: 23, color: '#000000', zIndex: 1 },
  subtitle: { position: 'absolute', left: 20, top: 63, fontFamily: type.familyMedium, fontSize: 11, lineHeight: 13, color: '#8E8E93', zIndex: 1 },
  loading: { position: 'absolute', top: 150, left: 0, right: 0 },
  empty: { position: 'absolute', left: 23, right: 22, top: 115, minHeight: 100, borderRadius: 10, backgroundColor: '#F7F7F7', alignItems: 'center', justifyContent: 'center', padding: 16 },
  detailEmpty: { top: 158 },
  emptyText: { fontFamily: type.family, fontSize: 12, lineHeight: 18, color: '#8E8E93', textAlign: 'center' },
  alertCard: { position: 'absolute', left: 23, right: 22, height: 115, borderRadius: 10, backgroundColor: '#F7F7F7', shadowColor: '#000', shadowOpacity: 0.1, shadowRadius: 10, shadowOffset: { width: 1, height: 1 } },
  trust: { position: 'absolute', left: 16, top: 15, height: 16, minWidth: 59, paddingHorizontal: 10, borderRadius: 20, backgroundColor: '#B0DB9C', alignItems: 'center', justifyContent: 'center' },
  trustText: { fontFamily: type.familyBold, fontSize: 10, lineHeight: 13, color: '#316837' },
  cardTitle: { position: 'absolute', left: 16, right: 28, top: 41, fontFamily: type.familyBold, fontSize: 17, lineHeight: 22, color: '#525253' },
  cardBody: { position: 'absolute', left: 16, top: 70, fontFamily: type.family, fontSize: 11, lineHeight: 13, color: '#525253' },
  chevron: { position: 'absolute', right: 14, top: 19, fontSize: 24, color: '#67AE6E' },
  header: { position: 'absolute', left: 0, right: 0, top: 0, height: 48, backgroundColor: '#FFFFFF', justifyContent: 'center', alignItems: 'center', zIndex: 1 },
  headerTitle: { fontFamily: type.familySemiBold, fontSize: 18, lineHeight: 23, color: '#000000' },
  back: { position: 'absolute', left: 12, top: 10, width: 24, height: 28, justifyContent: 'center' },
  backText: { fontSize: 34, lineHeight: 28, color: '#8E8E93', fontWeight: '300' },
  locationCard: { position: 'absolute', left: 23, right: 22, top: 59, height: 51, borderRadius: 10, backgroundColor: '#F7F7F7', justifyContent: 'center', paddingHorizontal: 16, zIndex: 1 },
  locationText: { fontFamily: type.familyBold, fontSize: 15, lineHeight: 19, color: '#525253' },
  reportCount: { position: 'absolute', left: 26, top: 131, fontFamily: type.family, fontSize: 11, lineHeight: 13, color: '#525253', zIndex: 1 },
  reportCard: { position: 'absolute', left: 23, right: 22, height: 66, borderRadius: 8, backgroundColor: '#F8F8F8', paddingHorizontal: 16, paddingTop: 12 },
  reportDate: { fontFamily: type.family, fontSize: 11, lineHeight: 13, color: '#4D4D4D' },
  reportText: { fontFamily: type.family, fontSize: 11, lineHeight: 13, color: '#4D4D4D', marginTop: 9 },
});
