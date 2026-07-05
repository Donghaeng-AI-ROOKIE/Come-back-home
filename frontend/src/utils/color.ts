/** 색 유틸 — 지도 폴리곤 fillColor 등에 rgba 문자열 생성. */
export function hexToRgba(hex: string, alpha: number): string {
  const h = hex.replace('#', '');
  const full = h.length === 3 ? h.split('').map((c) => c + c).join('') : h;
  const r = parseInt(full.slice(0, 2), 16);
  const g = parseInt(full.slice(2, 4), 16);
  const b = parseInt(full.slice(4, 6), 16);
  const a = Math.max(0, Math.min(1, alpha));
  return `rgba(${r}, ${g}, ${b}, ${a})`;
}

/** react-native-maps 좌표 변환: {lat,lng} → {latitude,longitude}. */
export function toLatLng(p: { lat: number; lng: number }): { latitude: number; longitude: number } {
  return { latitude: p.lat, longitude: p.lng };
}
