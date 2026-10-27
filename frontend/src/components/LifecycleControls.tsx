/** Owner actions are confirmed inline, including on web where native Alert differs. */
import React, { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useQueryClient } from '@tanstack/react-query';
import { closeCase, deleteCase, deletePersona, confirmPersona, Case, Persona } from '../api/guardian';
import { useAuthStore } from '../store/authStore';
import { useGuardianCaseStore } from '../store/guardianCaseStore';
import { useGuardianStore } from '../store/guardianStore';
import { refreshAfterCaseChange } from '../utils/caseRefresh';
import { serverTimeMs } from '../utils/walkFormat';
import { color, type } from '../theme/tokens';

/**
 * 버튼 모양. `plain` 은 등록 정보 카드(PersonaDetail)가 쓰는 원래 모양이고, 나머지는
 * 보호자 알림 탭의 사건 카드용이다 — 제보 카드와 같은 톤의 둥근 버튼.
 * 모양만 바꾼다. 두 번 눌러 확인하는 동작은 모든 모양이 같다.
 */
type ActionLook = 'plain' | 'primary' | 'secondary' | 'danger';

function Action({ label, run, explanation, look = 'plain' }: { label: string; run: () => Promise<void>; explanation: string; look?: ActionLook }) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const plain = look === 'plain';
  return <View style={plain ? { marginVertical: 6 } : styles.action}>
    {confirming ? <Text style={plain ? { marginBottom: 8 } : styles.explain}>{explanation}</Text> : null}
    {error ? <Text accessibilityRole="alert" style={plain ? { color: '#AD3333' } : styles.error}>{error}</Text> : null}
    <Pressable accessibilityRole="button" disabled={busy} style={plain ? { padding: 12, borderWidth: 1, borderColor: '#BBB', borderRadius: 8 } : [styles.button, buttonLook[look]]} onPress={async () => {
      if (!confirming) { setConfirming(true); return; }
      setBusy(true); setError('');
      try { await run(); setConfirming(false); } catch (e) { setError(e instanceof Error ? e.message : '처리하지 못했어요. 다시 시도해 주세요.'); }
      finally { setBusy(false); }
    }}><Text style={plain ? undefined : [styles.buttonText, textLook[look]]}>{busy ? '처리 중' : confirming ? `${label} 확인` : label}</Text></Pressable>
    {confirming && !busy ? <Pressable accessibilityRole="button" onPress={() => {setConfirming(false);setError('');}} style={plain ? { padding: 10 } : styles.cancel}><Text style={plain ? undefined : styles.cancelText}>취소</Text></Pressable> : null}
  </View>;
}
const card = { padding: 16, marginVertical: 12, borderWidth: 1, borderColor: '#DDD', borderRadius: 12 };

/** 사건 날짜 — `created_at` 은 오프셋 없는 서버 시각(UTC)이라 그대로 읽으면 한국 시간 0~9시 신고가 전날로 보인다. */
function caseDate(createdAt: string): string {
  return new Date(serverTimeMs(createdAt)).toLocaleDateString('ko-KR');
}

export function CaseLifecycleCard({ item }: { item: Case }) {
  const owner = useAuthStore(s => s.userId);
  const qc = useQueryClient();
  if (!owner) return null;
  const closed = ['found', 'closed'].includes(item.status);
  // 종결·삭제 직후 사건 목록을 바로 다시 받는다(이유는 utils/caseRefresh 주석).
  const refresh = () => refreshAfterCaseChange(qc);
  return <View style={styles.caseCard}>
    <View style={[styles.badge, closed ? styles.closedBadge : styles.activeBadge]}>
      <Text style={[styles.badgeText, closed ? styles.closedBadgeText : styles.activeBadgeText]}>{closed ? '종결' : '수색 중'}</Text>
    </View>
    <Text style={styles.caseTitle}>{closed ? '종결된 수색' : '진행 중인 수색'} · {caseDate(item.created_at)}</Text>
    {closed ? <>
      <Text style={styles.caseBody}>수색 알림과 지도 제공이 중단됐어요. 사건 정보는 종결 후 5일 이내 자동 파기되며, 지금 삭제할 수도 있어요.</Text>
      <Action look="danger" label="사건 정보 삭제" explanation="제보·예측 기록도 함께 삭제되며 되돌릴 수 없어요. 등록한 가족 정보는 유지돼요." run={async () => {
        await deleteCase(item.id, owner); useGuardianCaseStore.getState().removeCase(item.id);
        if (useGuardianStore.getState().caseId === item.id) useGuardianStore.getState().reset();
        await refresh();
      }} />
    </> : <>
      <Action look="primary" label="가족을 찾았어요" explanation="수색을 종결하고 시민 알림과 지도 제공을 중단해요. 실제로 가족을 찾았을 때 눌러 주세요." run={async () => {await closeCase(item.id, owner, 'found'); await refresh();}} />
      <Action look="secondary" label="신고 철회" explanation="수색을 종결하고 시민 알림과 지도 제공을 중단해요. 계속 수색이 필요하면 취소해 주세요." run={async () => {await closeCase(item.id, owner, 'withdrawn'); await refresh();}} />
    </>}
  </View>;
}

export function PersonaLifecycleCard({ item, onConfirmed, onDeleted }: { item: Persona; onConfirmed: (p: Persona) => void; onDeleted: () => void }) {
  const owner = useAuthStore(s => s.userId);
  const qc = useQueryClient();
  if (!owner) return null;
  const stamp = item.last_confirmed_at;
  return <View style={card}>
    <Text style={{ fontWeight: '700' }}>등록 정보 확인</Text>
    <Text>{stamp ? `마지막 확인: ${new Date(stamp).toLocaleDateString('ko-KR')}` : '등록 후 정보 확인 기록이 없어요.'}</Text>
    <Text>거주지·자주 가는 곳·행동이 달라졌다면 내용을 수정해 주세요. 수정 내용은 개인 해석과 진행 중인 수색에 반영돼요.</Text>
    <Action label="지금도 같은 정보예요" explanation="아래 정보를 확인했어요. 내용은 바꾸지 않고 확인 날짜만 기록해요." run={async () => {
      onConfirmed(await confirmPersona(item.id, owner)); await qc.invalidateQueries({ queryKey: ['personas'] });
    }} />
    <Action label="등록 정보 삭제" explanation="가족 정보와 인터뷰, 연결된 종결 사건을 함께 삭제해요. 되돌릴 수 없으며 진행 중인 수색은 먼저 종결해야 해요." run={async () => {
      await deletePersona(item.id, owner); await qc.cancelQueries(); qc.clear(); onDeleted();
    }} />
  </View>;
}

/**
 * 보호자 알림 탭의 사건 카드 — 같은 탭의 제보 카드(회색 #F7F7F7, 둥근 10, 그림자 0.1)와
 * 같은 톤이다. 예전에는 회색 테두리 상자라 탭 안에서 혼자 다른 화면처럼 보였다.
 */
const styles = StyleSheet.create({
  caseCard: { marginLeft: 23, marginRight: 22, marginTop: 14, borderRadius: 10, backgroundColor: '#F7F7F7', paddingHorizontal: 16, paddingTop: 15, paddingBottom: 12, shadowColor: '#000', shadowOpacity: 0.1, shadowRadius: 10, shadowOffset: { width: 1, height: 1 } },
  badge: { alignSelf: 'flex-start', height: 16, minWidth: 48, paddingHorizontal: 10, borderRadius: 20, alignItems: 'center', justifyContent: 'center' },
  activeBadge: { backgroundColor: '#B0DB9C' },
  closedBadge: { backgroundColor: '#E2E2E2' },
  badgeText: { fontFamily: type.familyCssBold, fontSize: 10, lineHeight: 13 },
  activeBadgeText: { color: '#316837' },
  closedBadgeText: { color: '#6B6B70' },
  caseTitle: { marginTop: 10, fontFamily: type.familyCssBold, fontSize: 15, lineHeight: 19, color: '#525253' },
  caseBody: { marginTop: 6, fontFamily: type.familyCss, fontSize: 11, lineHeight: 15, color: '#525253' },
  action: { marginTop: 10 },
  explain: { marginBottom: 8, fontFamily: type.familyCss, fontSize: 11, lineHeight: 15, color: '#525253' },
  error: { marginBottom: 8, fontFamily: type.familyCssBold, fontSize: 11, lineHeight: 15, color: '#AD3333' },
  button: { height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center' },
  buttonText: { fontFamily: type.familyCssBold, fontSize: 14, lineHeight: 18 },
  cancel: { height: 32, alignItems: 'center', justifyContent: 'center' },
  cancelText: { fontFamily: type.familyCssBold, fontSize: 12, lineHeight: 15, color: '#8E8E93' },
});
const buttonLook = StyleSheet.create({
  plain: {},
  primary: { backgroundColor: color.guardian },
  secondary: { backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#D8D8D8' },
  danger: { backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: color.figmaRed },
});
const textLook = StyleSheet.create({
  plain: {},
  primary: { color: '#FFFFFF' },
  secondary: { color: '#525253' },
  danger: { color: color.figmaRed },
});
