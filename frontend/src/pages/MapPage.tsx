import React, { useState, useEffect, useMemo } from 'react'
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet'
import L from 'leaflet'
import { MapPin, BarChart3, Wheat, AlertCircle } from 'lucide-react'
import type { RunSummary } from '../types'
import * as apiService from '../services/api'
import { REGIONS, CROP_TYPES } from '../constants/agriculture'
import 'leaflet/dist/leaflet.css'

const REGION_META: Record<string, { station: string; tav: number; amp: number }> = {
  henan: { station: '郑州', tav: 14.5, amp: 13.0 },
  shandong: { station: '济南', tav: 14.0, amp: 13.5 },
  heilongjiang: { station: '哈尔滨', tav: 4.5, amp: 16.0 },
  sichuan: { station: '成都', tav: 17.0, amp: 8.0 },
  hubei: { station: '武汉', tav: 17.0, amp: 12.0 },
  hunan: { station: '长沙', tav: 18.0, amp: 11.0 },
  jiangsu: { station: '南京', tav: 16.0, amp: 12.0 },
  anhui: { station: '合肥', tav: 16.0, amp: 12.0 },
  guangdong: { station: '广州', tav: 22.0, amp: 7.0 },
  xinjiang: { station: '乌鲁木齐', tav: 7.5, amp: 18.0 },
}

const regionIcon = new L.DivIcon({
  className: 'custom-marker',
  html: `<div style="width:24px;height:24px;border-radius:50%;background:#57534e;border:2px solid #fff;box-shadow:0 1px 3px rgba(0,0,0,0.3);display:flex;align-items:center;justify-content:center"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/></svg></div>`,
  iconSize: [24, 24],
  iconAnchor: [12, 24],
  popupAnchor: [0, -24],
})

function FlyToRegion({ lat, lng }: { lat: number; lng: number }) {
  const map = useMap()
  useEffect(() => {
    map.flyTo([lat, lng], 7, { duration: 1 })
  }, [lat, lng, map])
  return null
}

function matchRegion(run: RunSummary): string | null {
  const msg = (run.input_message || '').toLowerCase()
  const runAny = run as unknown as Record<string, unknown>
  const toolCalls = runAny.tool_calls as Array<Record<string, unknown>> | undefined
  if (toolCalls) {
    for (const tc of toolCalls) {
      const input = tc.input as Record<string, unknown> | undefined
      if (input && typeof input.region === 'string') {
        return input.region
      }
    }
  }
  for (const r of REGIONS) {
    if (msg.includes(r.id) || msg.includes(r.label)) {
      return r.id
    }
  }
  return null
}

const MapPage: React.FC = () => {
  const [selectedRegion, setSelectedRegion] = useState<string | null>(null)
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    apiService.getAllRuns(200, 0).then(data => {
      setRuns(data.items)
      setLoadError(null)
    }).catch(err => {
      setLoadError(err instanceof Error ? err.message : '加载分析记录失败')
    })
  }, [])

  const regionRuns = useMemo(() => {
    if (!selectedRegion) return []
    return runs.filter(r => matchRegion(r) === selectedRegion)
  }, [selectedRegion, runs])

  const regionRunCounts = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const r of REGIONS) {
      counts[r.id] = runs.filter(run => matchRegion(run) === r.id).length
    }
    return counts
  }, [runs])

  const selectedRegionData = selectedRegion
    ? { ...REGIONS.find(r => r.id === selectedRegion)!, ...REGION_META[selectedRegion] }
    : null

  const handleRegionClick = (regionId: string) => {
    setSelectedRegion(prev => prev === regionId ? null : regionId)
  }

  return (
    <div className="flex-1 overflow-hidden bg-stone-50 flex flex-col">
      <div className="px-4 sm:px-6 py-4 border-b border-stone-200/60 bg-white shrink-0">
        <div className="flex items-center gap-3">
          <MapPin size={20} className="text-stone-500" />
          <h1 className="text-lg font-semibold text-stone-800">地图可视化</h1>
          <span className="text-xs text-stone-400">点击地图标记查看区域分析历史</span>
        </div>
      </div>

      <div className="flex-1 flex overflow-hidden">
        <div className="flex-1 relative">
          <MapContainer
            center={[35.0, 113.0]}
            zoom={5}
            className="w-full h-full"
            style={{ minHeight: '400px' }}
          >
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
            {REGIONS.map(region => {
              const meta = REGION_META[region.id]
              return (
                <Marker
                  key={region.id}
                  position={[region.lat, region.lng]}
                  icon={regionIcon}
                  eventHandlers={{ click: () => handleRegionClick(region.id) }}
                >
                  <Popup>
                    <div className="text-sm">
                      <p className="font-semibold text-stone-800">{region.label}</p>
                      {meta && (
                        <>
                          <p className="text-xs text-stone-500">气象站: {meta.station}</p>
                          <p className="text-xs text-stone-500">年均温: {meta.tav}°C | 温幅: {meta.amp}°C</p>
                        </>
                      )}
                      <p className="text-xs text-stone-500">分析记录: {regionRunCounts[region.id] || 0} 条</p>
                    </div>
                  </Popup>
                </Marker>
              )
            })}
            {selectedRegionData && (
              <FlyToRegion lat={selectedRegionData.lat} lng={selectedRegionData.lng} />
            )}
          </MapContainer>
        </div>

        <div className="w-80 border-l border-stone-200/60 bg-white overflow-y-auto shrink-0">
          {selectedRegion && selectedRegionData ? (
            <div className="p-4 space-y-4">
              <div>
                <h2 className="text-base font-semibold text-stone-800 flex items-center gap-2">
                  <MapPin size={14} className="text-stone-500" />
                  {selectedRegionData.label}
                </h2>
                {'station' in selectedRegionData && (
                  <p className="text-xs text-stone-400 mt-1">
                    气象站: {selectedRegionData.station} | 年均温: {selectedRegionData.tav}°C
                  </p>
                )}
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div className="bg-stone-50 rounded-lg p-3">
                  <p className="text-lg font-semibold text-stone-800">{regionRunCounts[selectedRegion] || 0}</p>
                  <p className="text-xs text-stone-400">分析记录</p>
                </div>
                {'tav' in selectedRegionData && (
                  <div className="bg-stone-50 rounded-lg p-3">
                    <p className="text-lg font-semibold text-stone-800">{selectedRegionData.tav}°C</p>
                    <p className="text-xs text-stone-400">年均温度</p>
                  </div>
                )}
              </div>

              <div>
                <h3 className="text-xs font-medium text-stone-500 mb-2 flex items-center gap-1">
                  <BarChart3 size={12} /> 区域分析历史
                </h3>
                {loadError ? (
                  <div className="flex items-center gap-2 text-red-500 text-xs py-4 justify-center">
                    <AlertCircle size={14} /> {loadError}
                  </div>
                ) : regionRuns.length === 0 ? (
                  <p className="text-xs text-stone-400 py-4 text-center">暂无该区域的分析记录</p>
                ) : (
                  <div className="space-y-2">
                    {regionRuns.slice(0, 20).map(run => (
                      <div key={run.run_id} className="bg-stone-50 rounded-lg p-2.5">
                        <p className="text-xs text-stone-600 font-medium truncate">{run.input_message}</p>
                        <div className="flex items-center gap-2 mt-1">
                          <span className={`text-[9px] px-1.5 py-0 rounded-full font-medium ${
                            run.status === 'completed' ? 'bg-green-50 text-green-600' :
                            run.status === 'failed' ? 'bg-red-50 text-red-500' :
                            'bg-stone-100 text-stone-500'
                          }`}>
                            {run.status === 'completed' ? '完成' : run.status === 'failed' ? '失败' : run.status}
                          </span>
                          {run.model_name && (
                            <span className="text-[9px] text-stone-400">{run.model_name}</span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div>
                <h3 className="text-xs font-medium text-stone-500 mb-2 flex items-center gap-1">
                  <Wheat size={12} /> 支持作物
                </h3>
                <div className="flex flex-wrap gap-1.5">
                  {CROP_TYPES.map(crop => (
                    <span key={crop.id} className="text-[10px] px-2 py-1 bg-stone-100 text-stone-500 rounded-full">
                      {crop.label}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="p-4 text-center">
              <MapPin size={24} className="mx-auto text-stone-300 mb-3" />
              <p className="text-sm text-stone-400">点击地图上的标记</p>
              <p className="text-xs text-stone-300 mt-1">查看区域分析历史和作物信息</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default MapPage
