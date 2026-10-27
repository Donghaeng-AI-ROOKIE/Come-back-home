import React from 'react';
import { Image, Pressable, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { LinearGradient } from 'expo-linear-gradient';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { color, type } from '../theme/tokens';
import FigmaFlowTabBar from '../components/FigmaFlowTabBar';
import FigmaStatusBar from '../components/FigmaStatusBar';
import DoneLogo from '../../assets/figma/report-done-logo.svg';
import DoneHome from '../../assets/figma/report-done-home.svg';

const mascot = require('../../assets/figma/report-done-mascot.png');

export default function ReportDoneScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const goHome = () => navigation.navigate('CitizenTabs', { screen: 'Home' });

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <StatusBar style="dark" />
      <LinearGradient colors={['#ECFAE5', '#DDF6D2']} style={styles.gradient}>
        <FigmaStatusBar />
        <View style={styles.body}>
          <DoneLogo width={77} height={42} style={styles.logo} />
          <Image source={mascot} resizeMode="contain" style={styles.mascot} />
          <Text style={styles.title}>제보 접수 완료</Text>
          <Text style={styles.desc}>제보 내용을 저장했어요.{`\n`}내용 분석과 지도 반영은 서버에서 진행해요.</Text>

          <View style={styles.notice}>
            <Text style={styles.noticeTitle}>보호자가 오실 때까지 10분만 기다려주세요.</Text>
            <Text style={styles.noticeText}>당신의 따뜻한 관심이 누군가를 가족의 품으로 돌려보내는 결정적인 단서가 되었습니다.{`\n`}감사합니다.</Text>
          </View>

          {/* 위치 없는 제보는 수색지도에 반영되지 않는다 — 분포를 기울이려면 위치가, 출발점을
              옮기려면 시각까지 있어야 한다(backend phase3/tip_flow). 시민은 그걸 몰랐다
              (10/27 측정의 막연한 제보). 판정은 접수 뒤 서버에서 돌아 이 화면은 결과를
              모르므로, 이 제보가 반영됐는지가 아니라 일반 안내로만 쓴다. */}
          <Text style={styles.hint}>본 장소와 시각을 함께 알려 주시면{`\n`}수색지도에 반영돼요.</Text>

          <Pressable style={styles.done} onPress={goHome} accessibilityRole="button">
            <DoneHome width={14} height={14} color={color.brand} />
            <Text style={styles.doneText}>홈으로 돌아가기</Text>
          </Pressable>
        </View>
        <FigmaFlowTabBar mode="citizen" active="home" />
      </LinearGradient>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#ECFAE5' },
  gradient: { flex: 1 },
  body: { flex: 1, position: 'relative', alignItems: 'center' },
  logo: { position: 'absolute', top: 88 },
  mascot: { position: 'absolute', top: 172, width: 34, height: 42 },
  title: { position: 'absolute', top: 224, width: 305, textAlign: 'center', fontFamily: type.familyCssSemiBold, fontSize: 20, lineHeight: 25, letterSpacing: 0.38, color: '#000000' },
  desc: { position: 'absolute', top: 263, width: 252, textAlign: 'center', fontFamily: type.familyCssMedium, fontSize: 14, lineHeight: 18, color: '#525253' },
  notice: { position: 'absolute', top: 317, width: 330, height: 112, borderRadius: 10, backgroundColor: '#FFFFFF', alignItems: 'center', paddingTop: 14 },
  noticeTitle: { width: 296, textAlign: 'center', fontFamily: type.familyCss, fontSize: 13, lineHeight: 18, letterSpacing: -0.08, color: '#297057' },
  noticeText: { width: 296, textAlign: 'center', fontFamily: type.familyCss, fontSize: 13, lineHeight: 18, letterSpacing: -0.08, color: '#4D4D4D', marginTop: 8 },
  // 안내 카드(317~429)와 버튼(483) 사이. 두 줄(34)이라 버튼과 겹치지 않는다.
  hint: { position: 'absolute', top: 440, width: 300, textAlign: 'center', fontFamily: type.familyCss, fontSize: 12, lineHeight: 17, letterSpacing: -0.08, color: '#525253' },
  done: { position: 'absolute', top: 483, width: 255, height: 37, borderRadius: 30, backgroundColor: '#FFFFFF', flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, shadowColor: '#000000', shadowOpacity: 0.25, shadowRadius: 2, shadowOffset: { width: 1, height: 1 }, elevation: 3 },
  doneText: { fontFamily: type.familyCssMedium, fontSize: 14, lineHeight: 18, color: '#525253' },
});
