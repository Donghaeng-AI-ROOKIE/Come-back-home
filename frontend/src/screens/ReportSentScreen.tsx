import React, { useEffect } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { SvgXml } from 'react-native-svg';
import { icBroadcastGreenXml } from '../assets/guardianSvg';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { color, type } from '../theme/tokens';
import { useRunPrediction } from '../hooks/queries';
import { useGuardianCaseStore } from '../store/guardianCaseStore';
import FigmaLogo from '../components/FigmaLogo';
import FigmaFlowTabBar from '../components/FigmaFlowTabBar';
import FigmaStatusBar from '../components/FigmaStatusBar';

export default function ReportSentScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const { caseId } = useRoute<RouteProp<RootStackParamList, 'ReportSent'>>().params;
  const predict = useRunPrediction(caseId);
  const [guideOpen, setGuideOpen] = React.useState(false);
  const addCase = useGuardianCaseStore((s) => s.addCase);
  // 신고의 유일한 착지점 — 여기서 기기에 사건 id 를 적어 둬야 알림 탭이 이 사건의
  // 제보를 따라갈 수 있다(서버에 보호자-사건 바인딩이 없다).
  useEffect(() => { addCase(caseId); predict.mutate(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [caseId]);
  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <StatusBar style="dark" />
      <FigmaStatusBar />
      <View style={styles.body}>
        <FigmaLogo mode="guardian" />
        {/* '⌁' 는 폰 폰트에 없어 □ 로 깨진다 — 시안의 방송 아이콘 SVG 로 대체. */}
        <SvgXml xml={icBroadcastGreenXml} width={20} height={19} />
        <Text style={styles.title}>신고 접수 완료</Text>
        <View style={styles.steps}>
          <Step n="1" label="신고 접수" state="done" />
          <View style={styles.line} />
          <Step n="2" label="AI 예상 경로 분석" state={predict.isPending ? 'active' : 'done'} loading={predict.isPending} />
          <View style={styles.line} />
          <Step n="3" label="시민 제보" state={predict.isSuccess ? 'active' : 'todo'} />
        </View>
        <View style={styles.notice}>
          <Text style={styles.noticeTitle}>안내사항</Text>
          <Text style={styles.noticeText}>{predict.isError ? '신고는 접수됐습니다. AI 분석만 다시 시도해 주세요.' : '현재 AI가 실종자의 습관과 지형을 분석하여 이동 경로를 파악하고 있습니다. 인근 시민들의 제보가 확인되는 대로 안내해 드리겠습니다.'}</Text>
        </View>
        <View style={styles.actions}>
          {predict.isError ? <Pressable style={styles.retry} onPress={() => predict.mutate()}><Text style={styles.retryText}>AI 분석 다시 시도</Text></Pressable> : null}
          {/* 이 버튼은 지침을 보여주는 자리인데 **홈으로 보내고 있었다** — 눌러도
              지침이 안 뜬다는 제보(08-12)의 원인. 신고 직후 보호자가 무엇을 해야
              하는지가 이 화면에서 가장 필요한 정보라, 화면을 떠나지 않고 띄운다. */}
          <Pressable style={styles.guide} onPress={() => setGuideOpen(true)}>
            <Text style={styles.guideText}>✓ 치매 가족 실종시 행동 지침</Text>
          </Pressable>
        </View>
      </View>
      <GuideSheet open={guideOpen} onClose={() => setGuideOpen(false)} />
      <FigmaFlowTabBar mode="guardian" active="home" />
    </SafeAreaView>
  );
}

/**
 * 신고 직후 보호자가 지금 할 일 — 「치매 가족 실종시 행동 지침」.
 *
 * 예측이 도는 동안 보호자는 화면만 보며 기다리게 된다. 그 시간에 할 수 있는
 * 일이 실제로 있고, 그게 발견 확률을 크게 바꾼다. 화면을 떠나지 않고 덮어
 * 띄우는 이유 — 신고 진행 상황을 놓치면 안 되기 때문이다.
 *
 * 내용은 경찰청·중앙치매센터의 실종 대응 요령을 보호자가 이 자리에서 바로
 * 할 수 있는 것만 추려 옮긴 것이다. 의학적 판단은 담지 않는다.
 */
const GUIDE_STEPS: { head: string; body: string }[] = [
  { head: '1. 집 안과 건물부터 다시 봅니다',
    body: '화장실·베란다·계단·옥상·주차장 순으로 확인하세요. 실제로 집 안이나 건물 안에서 발견되는 경우가 적지 않습니다.' },
  { head: '2. 112에 신고합니다',
    body: '"치매 환자 실종"이라고 분명히 말하세요. 실종아동등 프로파일링 시스템에 등록되어 수색 지원을 받을 수 있습니다. 지문·사진을 사전등록해 두었다면 그 사실도 함께 알리세요.' },
  { head: '3. 마지막으로 본 시각과 옷차림을 지금 적어 두세요',
    body: '기억은 생각보다 빨리 흐려집니다. 상의·하의·신발 색과 소지품을 적어 두면 수색과 제보 확인이 훨씬 빨라집니다.' },
  { head: '4. 자주 가던 곳을 순서대로 확인합니다',
    body: '옛집, 옛 직장, 늘 가던 시장·공원·경로당 순으로 보세요. 치매가 있는 분은 낯선 곳보다 오래된 기억 속 장소로 향하는 경우가 많습니다.' },
  { head: '5. 주변 상점·경비실에 사진을 보여 주세요',
    body: 'CCTV 확인을 부탁하면 이동 방향을 좁힐 수 있습니다. 편의점·약국·버스 정류장처럼 사람이 상주하는 곳이 우선입니다.' },
  { head: '6. 혼자 찾지 마세요',
    body: '가족·이웃과 구역을 나누고, 한 명은 집에 남아 있으세요. 스스로 돌아오는 경우가 있습니다.' },
];

/**
 * `Modal` 을 쓰지 않는다 — **웹에서 앱 프레임을 벗어난다.**
 *
 * react-native-web 의 Modal 은 `document.body.appendChild` 로 **`#root` 바깥에**
 * 붙는다(ModalPortal.js). 그런데 이 앱은 375pt 시안을 `#root` 에 통째로 배율을
 * 걸어 폰 크기에 맞춘다(src/pwa.ts scaleToPhone). 그래서 모달만 배율도, 375
 * 캔버스 제약도 받지 못하고 창 전체 크기로 그려진다 — "화면에 안 맞고 확대돼
 * 보인다"는 제보(08-12)의 정체다.
 *
 * 화면 안에 절대배치 오버레이로 그리면 `#root` 안에 있으므로 배율과 캔버스를
 * 그대로 따른다. 이 시트는 이 화면만 덮으면 되므로 포털이 필요 없다.
 */
function GuideSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  if (!open) return null;
  return (
      <View style={styles.sheetBackdrop}>
        <View style={styles.sheet}>
          <Text style={styles.sheetTitle}>치매 가족 실종시 행동 지침</Text>
          <Text style={styles.sheetLead}>AI가 예상 경로를 분석하는 동안 아래를 함께 해 주세요.</Text>
          <ScrollView style={styles.sheetScroll} contentContainerStyle={styles.sheetScrollBody}>
            {GUIDE_STEPS.map((s) => (
              <View key={s.head} style={styles.guideItem}>
                <Text style={styles.guideHead}>{s.head}</Text>
                <Text style={styles.guideBody}>{s.body}</Text>
              </View>
            ))}
          </ScrollView>
          <Pressable style={styles.sheetClose} onPress={onClose}>
            <Text style={styles.sheetCloseText}>닫기</Text>
          </Pressable>
        </View>
      </View>
  );
}

function Step({ n, label, state, loading }: { n: string; label: string; state: 'done' | 'active' | 'todo'; loading?: boolean }) {
  const bg = state === 'done' ? '#62B270' : state === 'active' ? '#A7D88E' : color.figmaGray;
  return <View style={styles.step}><View style={[styles.circle, { backgroundColor: bg }]}>{loading ? <ActivityIndicator size="small" color="#FFFFFF" /> : <Text style={styles.n}>{n}</Text>}</View><Text style={[styles.stepLabel, state !== 'todo' && styles.stepOn]}>{label}</Text></View>;
}
const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: color.guardianWash }, body: { flex: 1, alignItems: 'center', paddingTop: 84 },
  signal: { fontFamily: type.family, fontSize: 31, lineHeight: 34, color: color.brand, marginTop: 8 },
  title: { fontFamily: type.familySemiBold, fontSize: 20, color: '#000000', marginTop: 7 },
  steps: { width: 292, flexDirection: 'row', alignItems: 'center', marginTop: 55 },
  step: { width: 76, alignItems: 'center' }, line: { flex: 1, height: 1, borderTopWidth: 1, borderStyle: 'dashed', borderColor: color.brand, marginTop: -18 },
  circle: { width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center' },
  n: { fontFamily: type.familyBold, fontSize: 17, lineHeight: 22, letterSpacing: -0.41, color: '#FFFFFF' }, stepLabel: { fontFamily: type.family, fontSize: 11, lineHeight: 13, letterSpacing: 0.07, color: color.figmaGray, marginTop: 6, textAlign: 'center' }, stepOn: { color: color.brand },
  notice: { width: 330, minHeight: 69, backgroundColor: '#FFFFFF', borderRadius: 10, marginTop: 61, padding: 14 },
  noticeTitle: { fontFamily: type.familySemiBold, fontSize: 11, lineHeight: 13, letterSpacing: 0.07, color: color.brand }, noticeText: { fontFamily: type.family, fontSize: 11, lineHeight: 13, letterSpacing: 0.07, color: '#525253', marginTop: 4 },
  // 두 버튼을 같은 레이아웃 묶음에 두어 짧은 화면에서도 서로 겹치지 않게 한다.
  actions: { position: 'absolute', bottom: 157, width: 255, alignItems: 'center', gap: 10 },
  retry: { minHeight: 38, backgroundColor: color.figmaRed, borderRadius: 20, paddingHorizontal: 20, paddingVertical: 10, alignItems: 'center', justifyContent: 'center', elevation: 2 }, retryText: { fontFamily: type.familySemiBold, fontSize: 12, color: '#FFFFFF' },
  guide: { width: 255, height: 38, borderRadius: 22, backgroundColor: '#FFFFFF', alignItems: 'center', justifyContent: 'center', shadowColor: '#000', shadowOpacity: 0.14, shadowRadius: 2, shadowOffset: { width: 0, height: 1 }, elevation: 2 },
  guideText: { fontFamily: type.family, fontSize: 13, lineHeight: 18, letterSpacing: -0.08, color: '#525253' },

  // 행동 지침 시트 — 신고 화면 위에 덮는다(진행 상황을 잃지 않게).
  // Modal 대신 화면 안에서 전체를 덮는다(위 GuideSheet 주석 참고).
  sheetBackdrop: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.35)', justifyContent: 'flex-end', zIndex: 20 },
  sheet: { backgroundColor: '#FFFFFF', borderTopLeftRadius: 18, borderTopRightRadius: 18, paddingTop: 20, paddingHorizontal: 20, paddingBottom: 16, maxHeight: '82%' },
  sheetTitle: { fontFamily: type.familyBold, fontSize: 17, lineHeight: 22, letterSpacing: -0.41, color: '#000000' },
  sheetLead: { fontFamily: type.family, fontSize: 12, lineHeight: 17, color: color.figmaGray, marginTop: 6 },
  sheetScroll: { marginTop: 14 },
  sheetScrollBody: { paddingBottom: 8 },
  guideItem: { marginBottom: 16 },
  guideHead: { fontFamily: type.familySemiBold, fontSize: 14, lineHeight: 19, color: color.brand },
  guideBody: { fontFamily: type.family, fontSize: 13, lineHeight: 19, color: '#525253', marginTop: 4 },
  sheetClose: { marginTop: 6, height: 46, borderRadius: 10, backgroundColor: color.brand, alignItems: 'center', justifyContent: 'center' },
  sheetCloseText: { fontFamily: type.familySemiBold, fontSize: 15, color: '#FFFFFF' },
});
