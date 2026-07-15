export function formatDate(value?: string | null): string {
  return value ? new Date(value).toLocaleString() : "暂无时间";
}
