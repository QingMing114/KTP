export function escapeHtml(value: string): string {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;")
}

export function buildArtifactOpenHref(artifact: { uri?: string }): string | null {
  const uri = artifact?.uri?.trim()
  if (!uri) return null
  if (uri.startsWith("mock://")) return null
  if (uri.startsWith("http://") || uri.startsWith("https://")) return uri
  if (uri.startsWith("/") || uri.startsWith("file://")) {
    return `/v2/artifacts/open?path=${encodeURIComponent(uri)}`
  }
  return null
}

export function isMockArtifact(artifact: { uri?: string }): boolean {
  const uri = artifact?.uri?.trim()
  return uri?.startsWith("mock://") ?? false
}

export function getArtifactLabel(artifact: { artifact_type?: string }): string {
  const t = artifact?.artifact_type ?? ""
  if (t === "report_card") return "查看报告"
  if (t === "visualization_card") return "查看仪表盘"
  if (t === "inference_card") return "查看推理结果"
  if (t === "registry_card") return "查看模型产物"
  return "打开产物"
}

export function truncateId(id: string, length = 8): string {
  return id?.slice(0, length) ?? ""
}

export function getStatusLabel(status: string): string {
  switch (status) {
    case "completed": return "完成"
    case "failed": return "失败"
    case "streaming": return "进行中"
    case "pending": return "等待中"
    default: return status
  }
}

export function getStatusStyle(status: string): string {
  switch (status) {
    case "completed": return "bg-emerald-50 text-emerald-600"
    case "failed": return "bg-red-50 text-red-600"
    default: return "bg-yellow-50 text-yellow-600"
  }
}

export function formatRelativeTime(dateStr?: string): string {
  if (!dateStr) return ""
  const date = new Date(dateStr)
  if (isNaN(date.getTime())) return ""
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffSec = Math.floor(diffMs / 1000)
  const diffMin = Math.floor(diffSec / 60)
  const diffHour = Math.floor(diffMin / 60)
  const diffDay = Math.floor(diffHour / 24)

  if (diffSec < 60) return "刚刚"
  if (diffMin < 60) return `${diffMin}分钟前`
  if (diffHour < 24) return `${diffHour}小时前`
  if (diffDay < 7) return `${diffDay}天前`
  return date.toLocaleDateString("zh-CN", { month: "short", day: "numeric" })
}
