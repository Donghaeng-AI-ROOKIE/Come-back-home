import { cellOf } from './h3cell';
import type { GeoPoint } from '../types/domain';
export type EntryTarget = {case_id:string; cells:string[]; resolution:number};
export function enteredTargets(point:GeoPoint|null,accuracy:number|null,observedAt:number|undefined,
  targets:EntryTarget[],now=Date.now()):string[] {
  if (!point || accuracy==null || !Number.isFinite(accuracy) || accuracy>80 || accuracy<0 || !observedAt
      || now-observedAt>60_000 || now<observedAt) return [];
  return targets.filter(t=>{const mine=cellOf(point,t.resolution);return mine!=null&&t.cells.includes(mine);}).map(t=>t.case_id);
}
