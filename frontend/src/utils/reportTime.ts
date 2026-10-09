/** Interpret an explicitly entered local sighting time; keep the UTC offset on wire. */
export function reportTimeIso(input: string, now = new Date()): string | null {
  const match = /^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})$/.exec(input.trim());
  if (!match) return null;
  const [year, month, day, hour, minute] = match.slice(1).map(Number);
  const date = new Date(year, month - 1, day, hour, minute);
  if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day
      || date.getHours() !== hour || date.getMinutes() !== minute || date > now) return null;
  return date.toISOString();
}
