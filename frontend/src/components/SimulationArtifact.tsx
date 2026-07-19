import React, { useState, useMemo } from 'react'
import { ChevronDown, Table2, BarChart3, Sprout } from 'lucide-react'

interface SimulationArtifactProps {
  title: string
  content: string
}

interface SimData {
  table_name: string
  row_count: number
  columns: string[]
  rows: Record<string, unknown>[]
}

function parseSimData(content: string): SimData | null {
  try {
    const data = JSON.parse(content)
    if (data && typeof data === 'object' && Array.isArray(data.columns) && Array.isArray(data.rows)) {
      return data as SimData
    }
    if (Array.isArray(data) && data.length > 0 && typeof data[0] === 'object') {
      return {
        table_name: '',
        row_count: data.length,
        columns: Object.keys(data[0]),
        rows: data,
      }
    }
    return null
  } catch {
    return null
  }
}

function isNumericColumn(rows: Record<string, unknown>[], col: string): boolean {
  let numCount = 0
  const sample = rows.slice(0, 10)
  for (const row of sample) {
    const v = row[col]
    if (v === null || v === undefined || v === '') continue
    if (typeof v === 'number' || (typeof v === 'string' && !isNaN(Number(v)))) numCount++
  }
  return numCount > sample.length * 0.5
}

function formatCellValue(v: unknown): string {
  if (v === null || v === undefined) return ''
  if (typeof v === 'number') return Number.isInteger(v) ? String(v) : v.toFixed(3)
  if (Array.isArray(v)) return `[${v.length} items]`
  return String(v)
}

function formatNumber(v: number): string {
  if (Number.isInteger(v)) return String(v)
  if (Math.abs(v) < 0.01) return v.toExponential(2)
  return v.toFixed(2)
}

const CHART_COLORS = [
  '#6366f1', '#8b5cf6', '#ec4899', '#f59e0b', '#10b981',
  '#06b6d4', '#f97316', '#84cc16', '#e11d48', '#7c3aed',
]

const SimulationTable: React.FC<{ data: SimData }> = ({ data }) => {
  const [page, setPage] = useState(0)
  const pageSize = 10
  const totalPages = Math.ceil(data.rows.length / pageSize)
  const pageRows = data.rows.slice(page * pageSize, (page + 1) * pageSize)

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[11px] border-collapse">
        <thead>
          <tr className="bg-stone-100/80">
            <th className="px-2 py-1.5 text-left font-medium text-stone-500 border-b border-stone-200/60 w-8">#</th>
            {data.columns.map((col) => (
              <th key={col} className="px-2 py-1.5 text-left font-medium text-stone-500 border-b border-stone-200/60 whitespace-nowrap max-w-[180px] overflow-hidden text-ellipsis">
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {pageRows.map((row, i) => (
            <tr key={i} className="hover:bg-stone-50/60 transition-colors">
              <td className="px-2 py-1 text-stone-400 border-b border-stone-100/40">{page * pageSize + i + 1}</td>
              {data.columns.map((col) => (
                <td key={col} className="px-2 py-1 text-stone-600 border-b border-stone-100/40 whitespace-nowrap max-w-[180px] overflow-hidden text-ellipsis" title={formatCellValue(row[col])}>
                  {formatCellValue(row[col])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {totalPages > 1 && (
        <div className="flex items-center justify-between px-2 py-1.5 text-[10px] text-stone-400">
          <span>{data.rows.length} 行，第 {page + 1}/{totalPages} 页</span>
          <div className="flex gap-1">
            <button onClick={() => setPage(Math.max(0, page - 1))} disabled={page === 0} className="px-1.5 py-0.5 rounded hover:bg-stone-100 disabled:opacity-30 transition-colors">上一页</button>
            <button onClick={() => setPage(Math.min(totalPages - 1, page + 1))} disabled={page >= totalPages - 1} className="px-1.5 py-0.5 rounded hover:bg-stone-100 disabled:opacity-30 transition-colors">下一页</button>
          </div>
        </div>
      )}
    </div>
  )
}

const SimulationChart: React.FC<{ data: SimData }> = ({ data }) => {
  const numericCols = useMemo(
    () => data.columns.filter((col) => isNumericColumn(data.rows, col)),
    [data.columns, data.rows]
  )

  const dateCol = useMemo(() => {
    const candidates = data.columns.filter(
      (col) => /date|today|time|day/i.test(col) && !isNumericColumn(data.rows, col)
    )
    return candidates[0] || null
  }, [data.columns, data.rows])

  const [selectedCols, setSelectedCols] = useState<string[]>(() => {
    const priorityPatterns = [
      /LAI/i, /Grain\.Wt/i, /Biomass.*Wt/i, /Yield/i,
      /Phenology\.Stage$/i, /LeafAreaIndex/i, /AboveGround.*Wt/i,
    ]
    const priority: string[] = []
    for (const pat of priorityPatterns) {
      const match = numericCols.find((c) => pat.test(c))
      if (match && !priority.includes(match)) priority.push(match)
    }
    return priority.length > 0 ? priority.slice(0, 4) : numericCols.slice(0, 3)
  })

  const toggleCol = (col: string) => {
    setSelectedCols((prev) =>
      prev.includes(col) ? prev.filter((c) => c !== col) : prev.length < 5 ? [...prev, col] : prev
    )
  }

  const chartData = useMemo(() => {
    if (selectedCols.length === 0) return null

    const rows = data.rows.slice(0, 100)
    const allValues: number[] = []
    for (const col of selectedCols) {
      for (const row of rows) {
        const v = Number(row[col])
        if (!isNaN(v) && isFinite(v)) allValues.push(v)
      }
    }
    if (allValues.length === 0) return null

    let minVal = allValues[0]
    let maxVal = allValues[0]
    for (let i = 1; i < allValues.length; i++) {
      if (allValues[i] < minVal) minVal = allValues[i]
      if (allValues[i] > maxVal) maxVal = allValues[i]
    }
    const range = maxVal - minVal || 1

    const svgW = 520
    const svgH = 180
    const padL = 50
    const padR = 15
    const padT = 15
    const padB = 30
    const plotW = svgW - padL - padR
    const plotH = svgH - padT - padB

    const lines = selectedCols.map((col, ci) => {
      const points: string[] = []
      const validRows = rows.filter((row) => {
        const v = Number(row[col])
        return !isNaN(v) && isFinite(v)
      })
      validRows.forEach((row, i) => {
        const v = Number(row[col])
        const x = padL + (i / Math.max(validRows.length - 1, 1)) * plotW
        const y = padT + plotH - ((v - minVal) / range) * plotH
        points.push(`${x.toFixed(1)},${y.toFixed(1)}`)
      })
      return { col, points: points.join(' '), color: CHART_COLORS[ci % CHART_COLORS.length] }
    })

    const yTicks = 5
    const yTickVals = Array.from({ length: yTicks + 1 }, (_, i) => minVal + (range * i) / yTicks)

    const xLabels = dateCol
      ? rows.filter((_, i) => i % Math.ceil(rows.length / 6) === 0).map((row) => String(row[dateCol] || '').slice(0, 10))
      : []

    return { svgW, svgH, padL, padR, padT, padB, plotW, plotH, lines, minVal, maxVal, yTickVals, xLabels, rows }
  }, [data.rows, selectedCols, dateCol])

  if (numericCols.length === 0) {
    return <div className="text-[11px] text-stone-400 p-3">无数值列可供绘图</div>
  }

  return (
    <div>
      <div className="flex flex-wrap gap-1 mb-2 px-1">
        {numericCols.map((col) => (
          <button
            key={col}
            onClick={() => toggleCol(col)}
            className={`text-[10px] px-1.5 py-0.5 rounded-full border transition-colors ${
              selectedCols.includes(col)
                ? 'bg-indigo-50 border-indigo-200 text-indigo-600'
                : 'bg-stone-50 border-stone-200/60 text-stone-400 hover:text-stone-600'
            }`}
          >
            {col.length > 25 ? col.slice(0, 22) + '...' : col}
          </button>
        ))}
      </div>
      {chartData ? (
        <div className="overflow-x-auto">
          <svg viewBox={`0 0 ${chartData.svgW} ${chartData.svgH}`} className="w-full max-w-[560px]" style={{ minHeight: 160 }}>
            <line x1={chartData.padL} y1={chartData.padT} x2={chartData.padL} y2={chartData.padT + chartData.plotH} stroke="#e7e5e4" strokeWidth="1" />
            <line x1={chartData.padL} y1={chartData.padT + chartData.plotH} x2={chartData.padL + chartData.plotW} y2={chartData.padT + chartData.plotH} stroke="#e7e5e4" strokeWidth="1" />
            {chartData.yTickVals.map((v, i) => {
              const y = chartData.padT + chartData.plotH - ((v - chartData.minVal) / (chartData.maxVal - chartData.minVal || 1)) * chartData.plotH
              return (
                <g key={i}>
                  <line x1={chartData.padL - 4} y1={y} x2={chartData.padL + chartData.plotW} y2={y} stroke="#f5f5f4" strokeWidth="0.5" />
                  <text x={chartData.padL - 6} y={y + 3} textAnchor="end" fontSize="8" fill="#a8a29e">{formatNumber(v)}</text>
                </g>
              )
            })}
            {chartData.lines.map((line, i) => (
              <polyline key={i} points={line.points} fill="none" stroke={line.color} strokeWidth="1.5" strokeLinejoin="round" />
            ))}
          </svg>
          <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1 px-1">
            {chartData.lines.map((line) => (
              <div key={line.col} className="flex items-center gap-1">
                <span className="w-2 h-0.5 rounded-full" style={{ backgroundColor: line.color }} />
                <span className="text-[9px] text-stone-400">{line.col.length > 30 ? line.col.slice(0, 27) + '...' : line.col}</span>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="text-[11px] text-stone-400 p-3">选择列以查看图表</div>
      )}
    </div>
  )
}

const SimulationArtifact: React.FC<SimulationArtifactProps> = ({ title, content }) => {
  const [expanded, setExpanded] = useState(false)
  const [viewMode, setViewMode] = useState<'table' | 'chart'>('table')

  const simData = useMemo(() => parseSimData(content), [content])

  if (!simData) {
    return (
      <div className="border rounded-lg p-3 bg-stone-50/60 border-stone-200/60">
        <div className="flex items-center gap-2 mb-1.5">
          <Sprout size={13} className="text-stone-400" />
          <span className="font-medium text-[13px] text-stone-700">{title}</span>
        </div>
        <div className="text-[12px] text-stone-500 whitespace-pre-wrap">{content}</div>
      </div>
    )
  }

  const tableName = simData.table_name || title.replace(/^APSIM 输出 - /, '')

  return (
    <div className="border rounded-lg overflow-hidden bg-white border-stone-200/60">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-2 text-[13px] text-stone-600 hover:bg-stone-50/60 transition-colors"
      >
        <ChevronDown size={13} className={`text-stone-400 transition-transform ${expanded ? 'rotate-180' : ''}`} />
        <Sprout size={13} className="text-emerald-500" />
        <span className="font-medium">{tableName}</span>
        <span className="text-[10px] text-stone-400 ml-1">{simData.row_count} 行 · {simData.columns.length} 列</span>
      </button>

      {expanded && (
        <div className="border-t border-stone-200/40">
          <div className="flex items-center gap-1 px-3 py-1.5 bg-stone-50/40 border-b border-stone-100/60">
            <button
              onClick={() => setViewMode('table')}
              className={`flex items-center gap-1 text-[11px] px-2 py-0.5 rounded transition-colors ${
                viewMode === 'table' ? 'bg-white text-stone-700 shadow-sm' : 'text-stone-400 hover:text-stone-600'
              }`}
            >
              <Table2 size={11} /> 表格
            </button>
            <button
              onClick={() => setViewMode('chart')}
              className={`flex items-center gap-1 text-[11px] px-2 py-0.5 rounded transition-colors ${
                viewMode === 'chart' ? 'bg-white text-stone-700 shadow-sm' : 'text-stone-400 hover:text-stone-600'
              }`}
            >
              <BarChart3 size={11} /> 图表
            </button>
          </div>
          <div className="p-2">
            {viewMode === 'table' ? (
              <SimulationTable data={simData} />
            ) : (
              <SimulationChart data={simData} />
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default SimulationArtifact
