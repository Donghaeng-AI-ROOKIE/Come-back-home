/** Interpret an explicitly entered local sighting time; keep the UTC offset on wire. */
export type ReportTimeCheck = { iso: string } | { error: 'format' | 'future' };

// 보호자는 "2026-10-29 1:00"처럼 한 자리 시를 그대로 적는다. 두 자리만 받던 때는 형식
// 오류였는데 문구가 "미래 시각은 사용할 수 없습니다"까지 한데 묶여 미래 시각으로 읽혔다
// (10/29 팀 점검). 월·일·시는 한두 자리, 날짜 구분자는 - . / 를 받는다.
const PATTERN = /^(\d{4})[-./](\d{1,2})[-./](\d{1,2})\s+(\d{1,2}):(\d{2})$/;

export function checkReportTime(input: string, now = new Date()): ReportTimeCheck {
  const match = PATTERN.exec(input.trim());
  if (!match) return { error: 'format' };
  const [year, month, day, hour, minute] = match.slice(1).map(Number);
  const date = new Date(year, month - 1, day, hour, minute);
  if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day
      || date.getHours() !== hour || date.getMinutes() !== minute) return { error: 'format' };
  if (date > now) return { error: 'future' };
  return { iso: date.toISOString() };
}

export function reportTimeIso(input: string, now = new Date()): string | null {
  const result = checkReportTime(input, now);
  return 'iso' in result ? result.iso : null;
}
