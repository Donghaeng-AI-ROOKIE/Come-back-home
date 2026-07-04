/** POA 등급 유틸 + 범례 라벨 (spec §4.2). */
import { poa } from './tokens';
import type { PoaTier } from '../types/domain';

export const poaMeta = poa;

export function tierForProb(prob: number): PoaTier {
  if (prob >= 0.7) return 'high';
  if (prob >= 0.4) return 'mid';
  if (prob >= 0.2) return 'low';
  return 'lowest';
}

export const TIER_LABEL: Record<PoaTier, string> = {
  high: '고',
  mid: '중',
  low: '저',
  lowest: '최저',
};

export const TIER_RANGE: Record<PoaTier, string> = {
  high: '70%+',
  mid: '40–70%',
  low: '20–40%',
  lowest: '<20%',
};

export const TIER_ORDER: PoaTier[] = ['high', 'mid', 'low', 'lowest'];
