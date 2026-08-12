import React from 'react';
import { Image, Pressable, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { LinearGradient } from 'expo-linear-gradient';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { type } from '../theme/tokens';
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
          <Text style={styles.desc}>제보해주신 정보는 AI 예측 동선 갱신과{`\n`}위치 분석에 즉시 반영됩니다.</Text>

          <View style={styles.notice}>
            <Text style={styles.noticeTitle}>보호자가 오실 때까지 10분만 기다려주세요.</Text>
            <Text style={styles.noticeText}>당신의 따뜻한 관심이 누군가를 가족의 품으로 돌려보내는 결정적인 단서가 되었습니다.{`\n`}감사합니다.</Text>
          </View>

          <Pressable style={styles.done} onPress={goHome} accessibilityRole="button">
            <DoneHome width={14} height={14} />
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
  title: { position: 'absolute', top: 224, width: 305, textAlign: 'center', fontFamily: type.familySemiBold, fontSize: 20, lineHeight: 25, color: '#000000' },
  desc: { position: 'absolute', top: 263, width: 252, textAlign: 'center', fontFamily: type.familyMedium, fontSize: 14, lineHeight: 18, color: '#525253' },
  notice: { position: 'absolute', top: 317, width: 330, height: 112, borderRadius: 10, backgroundColor: '#FFFFFF', alignItems: 'center', paddingTop: 14 },
  noticeTitle: { width: 296, textAlign: 'center', fontFamily: type.family, fontSize: 13, lineHeight: 18, color: '#297057' },
  noticeText: { width: 296, textAlign: 'center', fontFamily: type.family, fontSize: 13, lineHeight: 18, color: '#4D4D4D', marginTop: 8 },
  done: { position: 'absolute', top: 483, width: 255, height: 37, borderRadius: 30, backgroundColor: '#FFFFFF', flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, shadowColor: '#000000', shadowOpacity: 0.25, shadowRadius: 2, shadowOffset: { width: 1, height: 1 }, elevation: 3 },
  doneText: { fontFamily: type.familyMedium, fontSize: 14, lineHeight: 18, color: '#525253' },
});
