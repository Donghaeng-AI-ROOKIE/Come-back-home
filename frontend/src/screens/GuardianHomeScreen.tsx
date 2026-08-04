/**
 * 보호자 홈 (와이어프레임) — 사전등록과 긴급신고 두 갈래.
 *
 * 긴급 신고 버튼이 화면 맨 위에 있는 이유: 이 화면을 급하게 여는 사람은
 * 이미 실종 상황이다. 사전등록 안내를 위에 두면 그 순간에 읽히지 않는다.
 */
import React from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { color, radius, space, type } from '../theme/tokens';
import { useGuardianStore } from '../store/guardianStore';

export default function GuardianHomeScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const persona = useGuardianStore((s) => s.persona);

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <StatusBar style="dark" />
      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        <Text style={styles.title} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          보호자 홈
        </Text>

        <Pressable
          onPress={() => navigation.navigate('Report')}
          accessibilityRole="button"
          accessibilityLabel="즉시 긴급 실종 신고"
          accessibilityHint="실종 신고를 접수하고 AI 예측을 시작합니다"
          style={({ pressed }) => [styles.sos, pressed && styles.pressed]}
        >
          <Text style={styles.sosLabel} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            즉시 긴급 실종 신고
          </Text>
        </Pressable>

        <Pressable
          onPress={() => navigation.navigate('RegChat')}
          accessibilityRole="button"
          accessibilityLabel="안심 사전 등록하기"
          style={({ pressed }) => [styles.banner, pressed && styles.pressed]}
        >
          <Text style={styles.bannerTitle} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            안심 사전 등록하기
          </Text>
          <Text style={styles.bannerBody} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            평상시에 미리 등록해 두면 신고 즉시 그 정보로 예측을 시작합니다.
          </Text>
        </Pressable>

        <Text style={styles.section} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          사전 등록된 가족
        </Text>
        <View style={styles.card}>
          {persona ? (
            <View style={styles.profileRow}>
              <View style={styles.avatar}>
                <Text style={styles.avatarEmoji}>👴</Text>
              </View>
              <View style={styles.profileInfo}>
                <Text style={styles.profileName} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                  {persona.name} ({persona.age}세)
                </Text>
                <View style={styles.statusBadge}>
                  <Text style={styles.statusText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                    등록 완료
                  </Text>
                </View>
              </View>
            </View>
          ) : (
            <Text style={styles.empty} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              아직 등록된 가족이 없습니다. 사전 등록을 먼저 진행해 주세요.
            </Text>
          )}
        </View>

        <View style={styles.guide}>
          <Text style={styles.guideText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            사전 등록 정보는 예측의 개인화에 쓰입니다. 자주 가시던 장소와 평소 습관이
            자세할수록 수색 구역이 좁아집니다.
          </Text>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: color.surfaceAlt },
  scroll: { padding: space.xl, gap: space.md, paddingBottom: space.xxl },
  title: { fontSize: type.size.title, fontWeight: type.weight.black, color: color.text, fontFamily: type.family },
  section: { fontSize: type.size.label, fontWeight: type.weight.black, color: color.textCaption, fontFamily: type.family, marginTop: space.sm },

  sos: {
    minHeight: 68,
    borderRadius: radius.lg,
    backgroundColor: color.critical,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sosLabel: { fontSize: 19, fontWeight: type.weight.black, color: '#FFFFFF', fontFamily: type.family },

  banner: {
    backgroundColor: color.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: color.border,
    padding: space.lg,
    gap: space.xs,
  },
  bannerTitle: { fontSize: type.size.cardTitle, fontWeight: type.weight.black, color: color.text, fontFamily: type.family },
  bannerBody: { fontSize: type.size.caption, color: color.textBody, fontFamily: type.family, lineHeight: 20 },

  card: {
    backgroundColor: color.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: color.border,
    padding: space.lg,
  },
  profileRow: { flexDirection: 'row', alignItems: 'center', gap: space.lg },
  avatar: { width: 48, height: 48, borderRadius: 24, backgroundColor: color.surfaceAlt, alignItems: 'center', justifyContent: 'center' },
  avatarEmoji: { fontSize: 24 },
  profileInfo: { flex: 1, gap: space.xs },
  profileName: { fontSize: type.size.body, fontWeight: type.weight.bold, color: color.text, fontFamily: type.family },
  statusBadge: { alignSelf: 'flex-start', backgroundColor: color.walkWash, borderRadius: radius.pill, paddingHorizontal: space.md, paddingVertical: 3 },
  statusText: { fontSize: type.size.caption, fontWeight: type.weight.bold, color: color.walkInk, fontFamily: type.family },
  empty: { fontSize: type.size.label, color: color.textBody, fontFamily: type.family, lineHeight: 22 },

  guide: { backgroundColor: color.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: color.border, padding: space.lg },
  guideText: { fontSize: type.size.caption, color: color.textBody, fontFamily: type.family, lineHeight: 20 },
  pressed: { opacity: 0.85 },
});
