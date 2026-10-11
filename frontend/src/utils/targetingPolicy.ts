/** The server selects one resolution for registration, lookup and entry. */
export type TargetingPolicy = {
  target_res: 7 | 8 | 9;
  coverage: number | null;
  targeting_policy: string;
  location_ttl_seconds: number;
};

export function targetingResolution(value: unknown): 7 | 8 | 9 | null {
  if (value == null || typeof value !== 'object') return null;
  const resolution = (value as { target_res?: unknown }).target_res;
  return resolution === 7 || resolution === 8 || resolution === 9 ? resolution : null;
}
