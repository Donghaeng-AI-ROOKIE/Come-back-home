/**
 * 모드 파생 토큰팩 (spec §2.4). 모든 화면이 하드코딩 대신 useModeTheme()를 소비.
 * - accent: 셸/탭 강조색 — walk→그린, search→앰버
 * - severityColor: 긴급 강조 — critical→빨강, active→앰버
 */
import { useAppModeStore } from '../store/appModeStore';
import { color } from './tokens';
import type { AppMode, Severity } from '../types/domain';

export type ModeTokens = {
  mode: AppMode;
  severity: Severity;
  accent: string;
  accentInk: string;
  accentWash: string;
  severityColor: string;
  severityInk: string;
  severityWash: string;
};

export function computeModeTokens(mode: AppMode, severity: Severity): ModeTokens {
  const searching = { accent: color.search, accentInk: color.searchInk, accentWash: color.searchWash };
  if (mode === 'walk') {
    return {
      mode,
      severity,
      accent: color.walk,
      accentInk: color.walkInk,
      accentWash: color.walkWash,
      severityColor: color.walk,
      severityInk: color.walkInk,
      severityWash: color.walkWash,
    };
  }
  // search
  const isCritical = severity === 'critical';
  return {
    mode,
    severity,
    ...searching,
    severityColor: isCritical ? color.critical : color.search,
    severityInk: isCritical ? color.criticalInk : color.searchInk,
    severityWash: isCritical ? color.criticalWash : color.searchWash,
  };
}

export function useModeTheme(): ModeTokens {
  const mode = useAppModeStore((s) => s.mode);
  const severity = useAppModeStore((s) => s.severity);
  return computeModeTokens(mode, severity);
}

/** 운영자 다크 트리 토큰 (spec §4.6). 소비자 라이트와 격리. */
export const operatorTheme = {
  bg: color.operatorBg,
  surface: color.operatorSurface,
  surfaceAlt: color.operatorSurfaceAlt,
  border: color.operatorBorder,
  text: color.operatorText,
  textSec: color.operatorTextSec,
  accent: color.search, // 수색 진행 앰버
} as const;
