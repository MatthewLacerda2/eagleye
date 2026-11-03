/** Local date and time for a backend ISO timestamp, in the UI language. */
export function formatDateTime(iso: string | null, language: string): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat(language, {
    dateStyle: "short",
    timeStyle: "medium",
  }).format(new Date(iso));
}
