const zhCN: Record<string, string> = {
  "app.title": "KTP 农业遥感多智能体系统",
  "nav.chat": "对话",
  "nav.analysis": "分析工具",
  "nav.imageAnalysis": "影像分析",
  "nav.batchAnalysis": "批量分析",
  "nav.knowledge": "知识库",
  "nav.datasets": "数据集",
  "nav.map": "地图",
  "nav.skills": "技能中心",
  "nav.results": "分析结果",
  "nav.history": "运行历史",
  "nav.settings": "设置",
  "auth.login": "登录",
  "auth.register": "注册",
  "auth.logout": "退出",
  "auth.username": "用户名",
  "auth.password": "密码",
  "auth.expired": "认证已过期，请重新登录",
  "chat.placeholder": "输入消息，Ctrl+Enter 发送",
  "chat.send": "发送",
  "chat.stop": "停止生成",
  "chat.newSession": "新建对话",
  "chat.export": "导出",
  "chat.mode.chat": "对话模式",
  "chat.mode.task": "任务模式",
  "common.loading": "加载中...",
  "common.error": "出错了",
  "common.retry": "重试",
  "common.confirm": "确认",
  "common.cancel": "取消",
  "common.delete": "删除",
  "common.save": "保存",
  "common.close": "关闭",
  "knowledge.title": "知识库管理",
  "knowledge.search": "语义搜索",
  "knowledge.filter": "文档筛选",
  "knowledge.ingest": "摄取文档",
  "knowledge.delete.confirm": "确定删除此文档吗？此操作不可撤销。",
  "map.title": "地图可视化",
  "map.clickMarker": "点击地图标记查看区域分析历史",
  "image.title": "影像分析",
  "image.upload": "上传影像",
  "image.mock": "模拟模式",
  "batch.title": "批量分析",
  "batch.addTask": "添加任务",
  "batch.runAll": "执行全部",
  "batch.clear": "清空",
  "settings.title": "设置",
  "settings.apiKey": "API Key",
  "settings.backend": "后端状态",
}

type TranslationKey = keyof typeof zhCN

let currentLocale = "zh-CN"
const translations: Record<string, Record<string, string>> = {
  "zh-CN": zhCN,
}

export function t(key: string): string {
  return translations[currentLocale]?.[key] ?? key
}

export function setLocale(locale: string): void {
  if (translations[locale]) {
    currentLocale = locale
  }
}

export function getLocale(): string {
  return currentLocale
}

export function registerTranslations(locale: string, data: Record<string, string>): void {
  translations[locale] = { ...translations[locale], ...data }
}

export type { TranslationKey }
