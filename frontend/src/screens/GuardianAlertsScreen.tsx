/**
 * 보호자 알림 탭 — 진행 중 신고의 시민 제보 현황 (피그마 주석 "제보 받는 알림창 추가").
 *
 * 별도 통지 API 를 만들지 않았다 — `GET /phase1/cases/{id}` 응답에 tips 가
 * 이미 통째로 실려 오므로(백엔드 Case.tips), 신고한 기기가 기억해 둔 케이스
 * (guardianCaseStore)를 15초 주기로 다시 읽는 것으로 충분하다. 시민 경보
 * 폴링(ALERT_POLL_MS)과 같은 주기 — 보호자가 더 늦게 알아야 할 이유가 없다.
 *
 * 제보 원문(text)을 그대로 보여준다 — 이 화면의 독자는 해당 사건의 보호자
 * 본인이라 시민 트리의 익명화 원칙(이름 미노출)과는 층위가 다르다.
 */
import React from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { SvgXml } from 'react-native-svg';
import { useQuery } from '@tanstack/react-query';
import { color, space, type } from '../theme/tokens';
import { gColor, gFont } from '../theme/guardianTokens';
import { tabAlertXml, tintXml } from '../assets/guardianSvg';
import { getCase, type GuardianTip } from '../api/guardian';
import { useGuardianCaseStore } from '../store/guardianCaseStore';
import { ALERT_POLL_MS } from '../hooks/queries';

const STATUS_LABEL: Record<string, string> = {
  intake: '신고 접수됨',
  predicted: '예측 완료 — 시민 알림 준비',
  searching: '수색 진행 중',
  found: '발견되었습니다',
  closed: '수색 종결',
};

/** decision → 보호자에게 말이 되는 한 줄. 백엔드 TipDecision 참조. */
function decisionLabel(tip: GuardianTip): { label: string; strong: boolean } {
  switch (tip.decision) {
    case 'layer2':
      return { label: '목격 확정 — 이 위치 기준으로 경로를 다시 예측했습니다', strong: true };
    case 'layer1':
      return { label: '수색 범위 갱신에 반영되었습니다', strong: false };
    case 'discard':
      return { label: '신뢰도가 낮아 반영하지 않았습니다', strong: false };
    default:
      return { label: '검토 중', strong: false };
  }
}

function timeLabel(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${hh}:${mm}`;
}

function TipCard({ tip }: { tip: GuardianTip }) {
  const d = decisionLabel(tip);
  return (
    <View style={[styles.tipCard, d.strong && styles.tipCardStrong]}>
      <View style={styles.tipHead}>
        <Text style={styles.tipTime} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          {timeLabel(tip.created_at)}
        </Text>
        {tip.p != null && (
          <Text style={styles.tipTrust} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            신뢰도 {Math.round(tip.p * 100)}%
          </Text>
        )}
      </View>
      <Text style={styles.tipText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
        {tip.text}
      </Text>
      <Text
        style={[styles.tipDecision, d.strong && styles.tipDecisionStrong]}
        allowFontScaling
        maxFontSizeMultiplier={type.maxScale}
      >
        {d.label}
      </Text>
    </View>
  );
}

export default function GuardianAlertsScreen() {
  const caseId = useGuardianCaseStore((s) => s.lastCaseId);

  // 시민 쪽 useCase(['case', id])와 키를 나눈다 — 이쪽만 15초 폴링을 걸기 때문.
  const { data } = useQuery({
    queryKey: ['guardianCase', caseId],
    queryFn: () => getCase(caseId as string),
    enabled: !!caseId,
    refetchInterval: ALERT_POLL_MS,
  });

  const tips = (data?.tips ?? []).slice().reverse(); // 최신이 위로
  const statusLabel = data ? (STATUS_LABEL[data.status] ?? data.status) : null;

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <Text style={styles.title} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
        알림
      </Text>

      {!caseId || !data ? (
        <View style={styles.empty}>
          <SvgXml xml={tintXml(tabAlertXml, gColor.chip)} width={40} height={48} />
          <Text style={styles.emptyText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            아직 도착한 알림이 없습니다.
          </Text>
          <Text style={styles.emptyCaption} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            수색 진행 상황과 확인된 제보 소식을 이곳에서 알려드립니다.
          </Text>
        </View>
      ) : (
        <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
          <View style={[styles.statusCard, data.status === 'found' && styles.statusFound]}>
            <Text style={styles.statusKey} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              수색 상태
            </Text>
            <Text style={styles.statusVal} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              {statusLabel}
            </Text>
            <Text style={styles.statusSub} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              시민 제보 {tips.length}건
            </Text>
          </View>

          {tips.length === 0 ? (
            <Text style={styles.noTips} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              아직 접수된 제보가 없습니다. 제보가 들어오면 바로 이곳에 표시됩니다.
            </Text>
          ) : (
            tips.map((tip) => <TipCard key={tip.id} tip={tip} />)
          )}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: gColor.surface },
  title: {
    fontSize: type.size.title,
    fontWeight: type.weight.black,
    color: color.text,
    fontFamily: type.family,
    padding: space.xl,
  },
  empty: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: space.md, padding: space.xl },
  emptyText: { fontSize: type.size.body, fontWeight: type.weight.bold, color: gColor.textMuted, fontFamily: type.family },
  emptyCaption: { fontSize: type.size.caption, color: gColor.gray, fontFamily: type.family, textAlign: 'center', lineHeight: 20 },

  scroll: { paddingHorizontal: space.xl, paddingBottom: 120, gap: space.md },
  statusCard: { borderRadius: 12, padding: space.lg, backgroundColor: gColor.mint, gap: 4 },
  statusFound: { backgroundColor: gColor.cardGreen },
  statusKey: { fontSize: 11, color: gColor.inkGreen, fontFamily: gFont.medium },
  statusVal: { fontSize: 17, color: '#000000', fontFamily: gFont.semiBold },
  statusSub: { fontSize: 12, color: gColor.textMuted, fontFamily: gFont.regular },

  noTips: {
    fontSize: type.size.caption,
    color: gColor.gray,
    fontFamily: type.family,
    textAlign: 'center',
    lineHeight: 20,
    paddingTop: space.xl,
  },

  tipCard: {
    borderRadius: 12,
    padding: space.lg,
    backgroundColor: gColor.barBg,
    gap: 6,
  },
  tipCardStrong: { backgroundColor: gColor.bubbleBot },
  tipHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  tipTime: { fontSize: 11, color: gColor.gray, fontFamily: gFont.regular },
  tipTrust: { fontSize: 11, color: gColor.inkGreen, fontFamily: gFont.medium },
  tipText: { fontSize: 13, color: gColor.textValue, fontFamily: gFont.regular, lineHeight: 19 },
  tipDecision: { fontSize: 11, color: gColor.gray, fontFamily: gFont.regular },
  tipDecisionStrong: { color: gColor.progressGreen, fontFamily: gFont.medium },
});
