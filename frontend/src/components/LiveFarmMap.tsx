import { useEffect, useMemo, useRef } from 'react'
import L from 'leaflet'
import { GeoJSON, MapContainer, TileLayer, useMap } from 'react-leaflet'
import type { LatLngBoundsExpression } from 'leaflet'
import 'leaflet/dist/leaflet.css'
import 'leaflet-draw'
import 'leaflet-draw/dist/leaflet.draw.css'
import './LiveFarmMap.css'
import { MapPin } from 'lucide-react'
import type { LiveFarm } from '../services/spatialClient'
import { formatAoiArea, formatLeafletArea, validateAoiGeometry, type AoiGeometry } from '../utils/aoiGeometry'

export type { AoiGeometry } from '../utils/aoiGeometry'

// leaflet-draw 1.0.4 assigns to an undeclared `type` variable in strict-mode bundles.
L.GeometryUtil.readableArea = formatLeafletArea

L.drawLocal.draw.toolbar.buttons.polygon = '绘制多边形 AOI'
L.drawLocal.draw.toolbar.buttons.rectangle = '绘制矩形 AOI'
L.drawLocal.draw.handlers.polygon.tooltip.start = '点击开始绘制 AOI'
L.drawLocal.draw.handlers.polygon.tooltip.cont = '点击继续添加顶点'
L.drawLocal.draw.handlers.polygon.tooltip.end = '点击首个顶点完成绘制'
L.drawLocal.draw.handlers.rectangle.tooltip.start = '拖动绘制矩形 AOI'
L.drawLocal.edit.toolbar.buttons.edit = '编辑 AOI'
L.drawLocal.edit.toolbar.buttons.editDisabled = '暂无可编辑的 AOI'
L.drawLocal.edit.toolbar.buttons.remove = '删除 AOI'
L.drawLocal.edit.toolbar.buttons.removeDisabled = '暂无可删除的 AOI'

type Position = [number, number]

interface Props {
  farms: LiveFarm[]
  selectedFarmId: string
  onFarmSelect: (farmId: string) => void
  onAoiChange: (geometry: AoiGeometry | null, areaHectares: number | null) => void
  onAoiError: (message: string) => void
  clearVersion: number
  aoiAreaHectares: number | null
}

const defaultCenter: Position = [38.55, 101.3]

const aoiStyle: L.PathOptions = {
  color: '#67e8f9',
  weight: 3,
  fillColor: '#22d3ee',
  fillOpacity: 0.18,
}

function geometryPositions(geometry: unknown): Position[] {
  const value = geometry as { type?: string; coordinates?: unknown }
  if (value?.type !== 'Polygon' || !Array.isArray(value.coordinates) || !Array.isArray(value.coordinates[0])) return []
  return (value.coordinates[0] as unknown[]).flatMap((point) => {
    if (!Array.isArray(point) || typeof point[0] !== 'number' || typeof point[1] !== 'number') return []
    return [[point[1], point[0]] as Position]
  })
}

function FarmFocus({ farm }: { farm?: LiveFarm }) {
  const map = useMap()
  useEffect(() => {
    const points = farm ? geometryPositions(farm.geometry) : []
    const bounds: LatLngBoundsExpression | null = points.length ? points : null
    if (bounds) map.fitBounds(bounds, { padding: [44, 44], maxZoom: 13 })
  }, [farm, map])
  return null
}

function validationMessage(reason: 'invalid_geometry' | 'too_small' | 'self_intersection'): string {
  if (reason === 'too_small') return 'AOI 面积过小，请至少覆盖一个有效分析像元。'
  if (reason === 'self_intersection') return 'AOI 边界不能自相交，请调整顶点后重试。'
  return '无法识别该 AOI，请绘制一个有效的闭合区域。'
}

function DrawControl({ onAoiChange, onAoiError, clearVersion }: Pick<Props, 'onAoiChange' | 'onAoiError' | 'clearVersion'>) {
  const map = useMap()
  const drawnItemsRef = useRef<L.FeatureGroup | null>(null)
  const callback = useRef(onAoiChange)
  const errorCallback = useRef(onAoiError)
  const latestClearVersion = useRef(clearVersion)

  useEffect(() => { callback.current = onAoiChange }, [onAoiChange])
  useEffect(() => { errorCallback.current = onAoiError }, [onAoiError])

  useEffect(() => {
    const drawnItems = new L.FeatureGroup()
    drawnItemsRef.current = drawnItems
    map.addLayer(drawnItems)

    const control = new L.Control.Draw({
      position: 'topleft',
      draw: {
        polyline: false,
        marker: false,
        circle: false,
        circlemarker: false,
        rectangle: { shapeOptions: aoiStyle },
        polygon: {
          allowIntersection: false,
          showArea: true,
          shapeOptions: aoiStyle,
          drawError: { color: '#fb7185', timeout: 1800 },
        },
      },
      edit: {
        featureGroup: drawnItems,
        edit: { selectedPathOptions: { color: '#f8fafc', weight: 3, fillColor: '#22d3ee', fillOpacity: 0.24 } },
        remove: true,
      },
    })

    const publishLayer = (layer: L.Layer, removeInvalidLayer = false): boolean => {
      const geometry = (layer as L.Layer & { toGeoJSON: () => GeoJSON.Feature }).toGeoJSON().geometry
      const result = validateAoiGeometry(geometry)
      if (!result.valid) {
        if (removeInvalidLayer) drawnItems.removeLayer(layer)
        errorCallback.current(validationMessage(result.reason))
        return false
      }
      callback.current(result.geometry, result.areaHectares)
      return true
    }

    const created = (raw: L.LeafletEvent) => {
      const event = raw as L.DrawEvents.Created
      if (!publishLayer(event.layer)) return
      drawnItems.clearLayers()
      drawnItems.addLayer(event.layer)
    }
    const edited = (raw: L.LeafletEvent) => {
      const event = raw as L.DrawEvents.Edited
      let hasValidLayer = false
      event.layers.eachLayer((layer) => { hasValidLayer = publishLayer(layer, true) || hasValidLayer })
      if (!hasValidLayer) callback.current(null, null)
    }
    const deleted = () => callback.current(null, null)

    map.addControl(control)
    map.on(L.Draw.Event.CREATED, created)
    map.on(L.Draw.Event.EDITED, edited)
    map.on(L.Draw.Event.DELETED, deleted)

    return () => {
      map.off(L.Draw.Event.CREATED, created)
      map.off(L.Draw.Event.EDITED, edited)
      map.off(L.Draw.Event.DELETED, deleted)
      map.removeControl(control)
      map.removeLayer(drawnItems)
      drawnItemsRef.current = null
    }
  }, [map])

  useEffect(() => {
    if (latestClearVersion.current === clearVersion) return
    latestClearVersion.current = clearVersion
    drawnItemsRef.current?.clearLayers()
    callback.current(null, null)
  }, [clearVersion])

  return null
}

export default function LiveFarmMap({
  farms,
  selectedFarmId,
  onFarmSelect,
  onAoiChange,
  onAoiError,
  clearVersion,
  aoiAreaHectares,
}: Props) {
  const selectedFarm = farms.find((farm) => farm.farm_id === selectedFarmId)
  const mapFarms = useMemo(() => farms.map((farm) => ({
    ...farm,
    feature: { type: 'Feature' as const, properties: { farmId: farm.farm_id, name: farm.name }, geometry: farm.geometry },
  })), [farms])

  return <div className="absolute inset-0 z-30 bg-[#12382c]" aria-label="农场分析地图">
    <MapContainer center={defaultCenter} zoom={8} zoomControl className="ktp-live-map h-full w-full">
      <TileLayer attribution="&copy; OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
      <FarmFocus farm={selectedFarm} />
      <DrawControl onAoiChange={onAoiChange} onAoiError={onAoiError} clearVersion={clearVersion} />
      {mapFarms.map((farm) => <GeoJSON key={farm.farm_id} data={farm.feature as never} style={{ color: farm.farm_id === selectedFarmId ? '#86efac' : '#e2e8f0', weight: farm.farm_id === selectedFarmId ? 3 : 2, fillColor: '#10b981', fillOpacity: farm.farm_id === selectedFarmId ? 0.3 : 0.12 }} eventHandlers={{ click: () => onFarmSelect(farm.farm_id) }} />)}
    </MapContainer>
    <div className="pointer-events-none absolute bottom-5 right-5 z-[500] flex items-center gap-2 rounded-lg border border-white/15 bg-slate-950/80 px-3 py-2 text-[10px] text-slate-200 shadow-xl backdrop-blur">
      {aoiAreaHectares == null ? <span>尚未选择 AOI</span> : <><span className="rounded bg-cyan-300/15 px-1.5 py-0.5 font-medium text-cyan-100">当前 AOI</span><strong className="text-cyan-100">{formatAoiArea(aoiAreaHectares)}</strong><span className="text-slate-400">可编辑或删除</span></>}
    </div>
    <div className="pointer-events-none absolute left-16 top-5 z-[500] rounded-lg bg-slate-950/75 px-2.5 py-1.5 text-[10px] text-slate-100 shadow-lg"><MapPin size={12} className="mr-1 inline text-emerald-300" />农场边界来自后端 GeoJSON</div>
  </div>
}
