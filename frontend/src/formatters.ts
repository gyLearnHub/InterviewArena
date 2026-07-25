export function parseApiDate(value: string): Date {
  const normalized = /(?:Z|[+-]\d{2}:\d{2})$/i.test(value) ? value : `${value}Z`;
  return new Date(normalized);
}

export function formatDate(value?: string | null): string {
  return value ? parseApiDate(value).toLocaleString() : "暂无时间";
}
