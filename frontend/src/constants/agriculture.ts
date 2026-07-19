export interface RegionInfo {
  id: string
  label: string
  lat: number
  lng: number
}

export const REGIONS: RegionInfo[] = [
  { id: "henan", label: "河南", lat: 34.76, lng: 113.65 },
  { id: "shandong", label: "山东", lat: 36.67, lng: 117.00 },
  { id: "heilongjiang", label: "黑龙江", lat: 45.75, lng: 126.65 },
  { id: "sichuan", label: "四川", lat: 30.57, lng: 104.07 },
  { id: "hubei", label: "湖北", lat: 30.59, lng: 114.31 },
  { id: "hunan", label: "湖南", lat: 28.23, lng: 112.94 },
  { id: "jiangsu", label: "江苏", lat: 32.06, lng: 118.80 },
  { id: "anhui", label: "安徽", lat: 31.82, lng: 117.23 },
  { id: "guangdong", label: "广东", lat: 23.13, lng: 113.26 },
  { id: "xinjiang", label: "新疆", lat: 43.79, lng: 87.63 },
]

export const CROP_TYPES = [
  { id: "wheat", label: "小麦" },
  { id: "corn", label: "玉米" },
  { id: "rice", label: "水稻" },
  { id: "soybean", label: "大豆" },
  { id: "cotton", label: "棉花" },
  { id: "rapeseed", label: "油菜" },
]

export const TASK_TYPES = [
  { id: "crop_health_detection", label: "作物健康检测" },
  { id: "lai_estimation", label: "LAI估算" },
  { id: "baldness_detection", label: "斑秃识别" },
  { id: "growth_monitoring", label: "生长监测" },
  { id: "yield_prediction", label: "产量预测" },
]

export function getRegionLabel(id: string): string {
  return REGIONS.find(r => r.id === id)?.label ?? id
}

export function getCropLabel(id: string): string {
  return CROP_TYPES.find(c => c.id === id)?.label ?? id
}

export function getTaskLabel(id: string): string {
  return TASK_TYPES.find(t => t.id === id)?.label ?? id
}
