export const WORKSPACE_TASKS = [
  { id: 'lai', title: '叶面积指数反演', description: '生成 LAI 地图与分析报告', status: '可执行', available: true },
  { id: 'crop', title: '农作物识别', description: '识别选区内的作物类型', status: '可执行', available: true },
  { id: 'growth', title: '作物长势评估', description: '基于 LAI 与植被覆盖分析当前长势', status: '可执行', available: true },
  { id: 'potential', title: '遥感冠层指数', description: '单景 NDVI + LAI，输出未校准的 0–100 分；不能替代估产', status: '试验', available: true },
  { id: 'yield_simple', title: '自动简化估产', description: '小麦/玉米自动识别生长季，获取辐射；粮食干重试验估计', status: '试验 · 自动采集', available: true },
  { id: 'yield', title: 'APSIM 产量估计', description: '按识别作物运行真实示例，或使用核验资料进行地块情景估产', status: '真实模拟 · 支持示例', available: true },
  { id: 'forecast', title: '生长变量预估', description: '结合时序与农学数据进行预测', status: '未开放', available: false },
] as const
