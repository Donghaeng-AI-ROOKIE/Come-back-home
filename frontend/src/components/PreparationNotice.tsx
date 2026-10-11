import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useMutation, useQuery } from '@tanstack/react-query';
import { getPreparationStatus, retryPreparation } from '../api/guardian';

/** Stored profile preparation, not a promise that a published map includes it. */
export default function PreparationNotice({ personaId }: { personaId: string }) {
  const status = useQuery({ queryKey: ['preparation', personaId],
    queryFn: () => getPreparationStatus(personaId),
    refetchInterval: q => {
      const s = q.state.data;
      return !s || [s.initial_state, s.mind_state].some(x => ['queued', 'running'].includes(x)) ? 5000 : false;
    } });
  const retry = useMutation({ mutationFn: () => retryPreparation(personaId),
    onSuccess: () => status.refetch() });
  const s = status.data;
  const busy = s && [s.initial_state, s.mind_state].some(x => ['queued', 'running'].includes(x));
  const ready = s?.initial_state === 'ready' && ['ready', 'ready_partial'].includes(s.mind_state);
  // Non-action notes also contain identity/history; their count is not a failure rate.
  const partial = s?.partial;
  const message = status.isError ? '개인 특성 준비 상태를 확인하지 못했습니다.'
    : !s ? '개인 특성 준비 상태를 확인하고 있습니다.'
    : busy ? '개인 특성을 준비하고 있습니다. 화면을 닫아도 계속되며, 신고는 먼저 할 수 있습니다.'
    : ready ? (partial ? '확인된 개인 특성을 저장했습니다. 일부 행동은 아직 반영되지 않아 제외했습니다.'
      : '개인 특성을 저장했습니다. 신고 후 예측에 사용할 수 있습니다.')
    : s.can_retry ? '개인 특성 준비가 완료되지 않았습니다. 저장된 등록 정보로 다시 준비할 수 있습니다.'
    : '개인 특성 준비가 아직 완료되지 않았습니다. 신고는 먼저 할 수 있습니다.';
  return <View style={styles.box} accessibilityLiveRegion="polite">
    <Text style={styles.text}>{message}</Text>
    {s?.can_retry ? <Pressable accessibilityRole="button" disabled={retry.isPending}
      onPress={() => retry.mutate()} style={styles.button}>
      <Text>{retry.isPending ? '준비 요청 중' : '개인 특성 다시 준비'}</Text>
    </Pressable> : null}
    {status.isError ? <Pressable accessibilityRole="button" onPress={() => status.refetch()}><Text>상태 다시 확인</Text></Pressable> : null}
    {retry.isError ? <Text style={styles.text}>준비 요청을 보내지 못했습니다. 다시 시도해 주세요.</Text> : null}
  </View>;
}

const styles = StyleSheet.create({
  box: { padding: 12, backgroundColor: '#F1F5F1', borderRadius: 8, marginVertical: 8 },
  text: { fontSize: 12, lineHeight: 18, color: '#334A38' },
  button: { paddingVertical: 10 },
});
