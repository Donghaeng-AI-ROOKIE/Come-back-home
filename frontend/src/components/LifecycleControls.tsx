/** Owner actions are confirmed inline, including on web where native Alert differs. */
import React, { useState } from 'react';
import { Pressable, Text, View } from 'react-native';
import { useQueryClient } from '@tanstack/react-query';
import { closeCase, deleteCase, deletePersona, confirmPersona, Case, Persona } from '../api/guardian';
import { useAuthStore } from '../store/authStore';
import { useGuardianCaseStore } from '../store/guardianCaseStore';
import { useGuardianStore } from '../store/guardianStore';

function Action({ label, run, explanation }: { label: string; run: () => Promise<void>; explanation: string }) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  return <View style={{ marginVertical: 6 }}>
    {confirming ? <Text style={{ marginBottom: 8 }}>{explanation}</Text> : null}
    {error ? <Text accessibilityRole="alert" style={{ color: '#AD3333' }}>{error}</Text> : null}
    <Pressable accessibilityRole="button" disabled={busy} style={{ padding: 12, borderWidth: 1, borderColor: '#BBB', borderRadius: 8 }} onPress={async () => {
      if (!confirming) { setConfirming(true); return; }
      setBusy(true); setError('');
      try { await run(); setConfirming(false); } catch (e) { setError(e instanceof Error ? e.message : '처리하지 못했어요. 다시 시도해 주세요.'); }
      finally { setBusy(false); }
    }}><Text>{busy ? '처리 중' : confirming ? `${label} 확인` : label}</Text></Pressable>
    {confirming && !busy ? <Pressable accessibilityRole="button" onPress={() => {setConfirming(false);setError('');}} style={{ padding: 10 }}><Text>취소</Text></Pressable> : null}
  </View>;
}
const card = { padding: 16, marginVertical: 12, borderWidth: 1, borderColor: '#DDD', borderRadius: 12 };

export function CaseLifecycleCard({ item }: { item: Case }) {
  const owner = useAuthStore(s => s.userId);
  const qc = useQueryClient();
  if (!owner) return null;
  const closed = ['found', 'closed'].includes(item.status);
  const refresh = async () => { await qc.cancelQueries(); qc.clear(); };
  return <View style={card}>
    <Text style={{ fontWeight: '700' }}>{closed ? '종결된 수색' : '진행 중인 수색'} · {new Date(item.created_at).toLocaleDateString('ko-KR')}</Text>
    {closed ? <>
      <Text>수색 알림과 지도 제공이 중단됐어요. 사건 정보는 종결 후 5일 이내 자동 파기되며, 지금 삭제할 수도 있어요.</Text>
      <Action label="사건 정보 삭제" explanation="제보·예측 기록도 함께 삭제되며 되돌릴 수 없어요. 등록한 가족 정보는 유지돼요." run={async () => {
        await deleteCase(item.id, owner); useGuardianCaseStore.getState().removeCase(item.id);
        if (useGuardianStore.getState().caseId === item.id) useGuardianStore.getState().reset();
        await refresh();
      }} />
    </> : <>
      <Action label="가족을 찾았어요" explanation="수색을 종결하고 시민 알림과 지도 제공을 중단해요. 실제로 가족을 찾았을 때 눌러 주세요." run={async () => {await closeCase(item.id, owner, 'found'); await refresh();}} />
      <Action label="신고 철회" explanation="수색을 종결하고 시민 알림과 지도 제공을 중단해요. 계속 수색이 필요하면 취소해 주세요." run={async () => {await closeCase(item.id, owner, 'withdrawn'); await refresh();}} />
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
