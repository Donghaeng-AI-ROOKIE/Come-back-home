/** 사전 등록 완료 (와이어프레임) — 무엇이 저장됐는지 보호자가 확인하는 화면. */
import React from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { color, radius, space, type } from '../theme/tokens';
import CTAButton from '../components/CTAButton';

function Row({ k, v }: { k: string; v: string }) {
  return (
    <View style={styles.row}>
      <Text style={styles.rowKey} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
        {k}
      </Text>
      <Text style={styles.rowVal} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
        {v}
      </Text>
    </View>
  );
}

export default function RegDoneScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const { name, age } = useRoute<RouteProp<RootStackParamList, 'RegDone'>>().params;

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
      <StatusBar style="dark" />
      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        <View style={styles.hero}>
          <Text style={styles.heroTitle} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            사전 등록이 끝났습니다
          </Text>
          <Text style={styles.heroSub} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            신고 시 이 정보로 바로 예측을 시작합니다.
          </Text>
        </View>

        <View style={styles.card}>
          <Row k="이름 / 연령" v={`${name} (${age}세)`} />
          <Row k="유형" v="치매" />
        </View>

        <View style={styles.notice}>
          <Text style={styles.noticeText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            등록 정보는 실종 상황의 예측에만 쓰이며, 사건이 종결되면 보관 기간에 따라 파기됩니다.
          </Text>
        </View>
      </ScrollView>

      <View style={styles.footer}>
        <CTAButton
          label="홈으로 돌아가기"
          onPress={() => navigation.navigate('GuardianTabs', { screen: 'GuardianHome' })}
          accent={color.walk}
        />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: color.surfaceAlt },
  scroll: { padding: space.xl, gap: space.lg },
  hero: { alignItems: 'center', gap: space.xs, paddingVertical: space.xl },
  heroTitle: { fontSize: 24, fontWeight: type.weight.black, color: color.text, fontFamily: type.family },
  heroSub: { fontSize: type.size.label, color: color.textBody, fontFamily: type.family, textAlign: 'center' },

  card: { backgroundColor: color.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: color.border, padding: space.lg },
  row: { flexDirection: 'row', paddingVertical: space.sm, gap: space.lg },
  rowKey: { width: 90, fontSize: type.size.caption, fontWeight: type.weight.bold, color: color.textCaption, fontFamily: type.family },
  rowVal: { flex: 1, fontSize: type.size.label, fontWeight: type.weight.medium, color: color.text, fontFamily: type.family },

  notice: { backgroundColor: color.walkWash, borderRadius: radius.lg, padding: space.lg },
  noticeText: { fontSize: type.size.caption, color: color.walkInk, fontFamily: type.family, lineHeight: 20 },

  footer: { padding: space.xl, borderTopWidth: 1, borderTopColor: color.border, backgroundColor: color.surface },
});
