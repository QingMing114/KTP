import { FormEvent, useEffect, useState } from 'react'
import {
  Activity,
  BarChart3,
  CalendarDays,
  CheckCircle2,
  ExternalLink,
  FileText,
  FlaskConical,
  Leaf,
  Loader2,
  Play,
  Sprout,
} from 'lucide-react'
import {
  createApsimYieldReport,
  loadApsimReportObjectUrl,
  type ApsimYieldReportRequest,
  type ApsimYieldReportResponse,
} from '../services/canonical/apsimClient'

const initialRequest: ApsimYieldReportRequest = {
  mode: 'demo',
  crop_type: 'wheat',
  region: 'henan',
  start_year: new Date().getFullYear() - 1,
  end_year: new Date().getFullYear(),
  cultivar: '',
  sowing_date: '',
}

export default function YieldEstimatePage() {
  const [request, setRequest] = useState(initialRequest)
  const [result, setResult] = useState<ApsimYieldReportResponse | null>(null)
  const [reportUrl, setReportUrl] = useState('')
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => () => {
    if (reportUrl) URL.revokeObjectURL(reportUrl)
  }, [reportUrl])

  const update = <K extends keyof ApsimYieldReportRequest>(
    key: K,
    value: ApsimYieldReportRequest[K],
  ) => setRequest((current) => ({ ...current, [key]: value }))

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (running) return
    setRunning(true)
    setError('')
    setResult(null)
    if (reportUrl) {
      URL.revokeObjectURL(reportUrl)
      setReportUrl('')
    }
    try {
      const response = await createApsimYieldReport(request)
      const objectUrl = await loadApsimReportObjectUrl(response.artifact.view_url)
      setResult(response)
      setReportUrl(objectUrl)
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : '产量估计未能完成')
    } finally {
      setRunning(false)
    }
  }

  const isDemo = request.mode === 'demo'

  return (
    <div className="flex-1 overflow-auto bg-stone-50">
      <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 sm:py-8">
        <header className="mb-6 flex flex-col justify-between gap-4 lg:flex-row lg:items-end">
          <div>
            <div className="mb-2 flex items-center gap-2 text-xs font-medium text-emerald-700">
              <Sprout size={15} />
              APSIM CROP MODEL
            </div>
            <h1 className="text-2xl font-semibold text-stone-800">作物产量估计</h1>
            <p className="mt-1 text-sm text-stone-500">
              调用 APSIM 生长模型，生成产量、LAI、生物量和生育阶段报告。
            </p>
          </div>
          <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-xs text-emerald-800">
            <span className="font-semibold">报告格式</span>
            <span className="ml-2 text-emerald-700">交互式 HTML · 可独立展示</span>
          </div>
        </header>

        <div className="grid gap-6 xl:grid-cols-[360px_minmax(0,1fr)]">
          <form onSubmit={submit} className="h-fit rounded-2xl border border-stone-200 bg-white p-5 shadow-sm">
            <h2 className="text-sm font-semibold text-stone-800">模拟配置</h2>
            <p className="mt-1 text-xs leading-5 text-stone-500">先用验证数据快速演示，部署 APSIM Models 后可切换实时模拟。</p>

            <div className="mt-5 grid grid-cols-2 gap-2">
              <ModeButton
                active={isDemo}
                icon={<FlaskConical size={16} />}
                title="验证数据"
                description="立即生成"
                onClick={() => update('mode', 'demo')}
              />
              <ModeButton
                active={!isDemo}
                icon={<Activity size={16} />}
                title="实时模拟"
                description="需要运行时"
                onClick={() => update('mode', 'simulation')}
              />
            </div>

            {isDemo ? (
              <div className="mt-5 rounded-xl border border-emerald-200/80 bg-emerald-50/70 p-4">
                <div className="flex items-center gap-2 text-sm font-medium text-emerald-900">
                  <CheckCircle2 size={16} />
                  Wheat GxExM 验证案例
                </div>
                <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
                  <div><dt className="text-emerald-700/70">作物</dt><dd className="mt-0.5 font-medium text-emerald-950">小麦</dd></div>
                  <div><dt className="text-emerald-700/70">品种</dt><dd className="mt-0.5 font-medium text-emerald-950">Hartog</dd></div>
                  <div><dt className="text-emerald-700/70">数据期</dt><dd className="mt-0.5 font-medium text-emerald-950">2014–2015</dd></div>
                  <div><dt className="text-emerald-700/70">来源</dt><dd className="mt-0.5 font-medium text-emerald-950">APSIM SQLite</dd></div>
                </dl>
              </div>
            ) : (
              <div className="mt-5 space-y-4">
                <Field label="作物类型">
                  <select value={request.crop_type} onChange={(event) => update('crop_type', event.target.value as ApsimYieldReportRequest['crop_type'])} className={inputClass}>
                    <option value="wheat">小麦 Wheat</option>
                    <option value="maize">玉米 Maize</option>
                    <option value="soybean">大豆 Soybean</option>
                  </select>
                </Field>
                <Field label="模拟区域">
                  <select value={request.region} onChange={(event) => update('region', event.target.value)} className={inputClass}>
                    <option value="henan">河南</option>
                    <option value="shandong">山东</option>
                    <option value="hebei">河北</option>
                    <option value="gansu">甘肃</option>
                  </select>
                </Field>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="开始年份">
                    <input type="number" min={1900} max={2200} value={request.start_year} onChange={(event) => update('start_year', Number(event.target.value))} className={inputClass} />
                  </Field>
                  <Field label="结束年份">
                    <input type="number" min={1900} max={2200} value={request.end_year} onChange={(event) => update('end_year', Number(event.target.value))} className={inputClass} />
                  </Field>
                </div>
                <Field label="播种日期">
                  <input type="date" value={request.sowing_date} onChange={(event) => update('sowing_date', event.target.value)} className={inputClass} />
                </Field>
                <Field label="品种（可选）">
                  <input value={request.cultivar} onChange={(event) => update('cultivar', event.target.value)} placeholder="留空使用区域默认品种" className={inputClass} />
                </Field>
                <p className="rounded-lg bg-amber-50 px-3 py-2 text-[11px] leading-5 text-amber-700">
                  实时模拟要求后端已配置 APSIM_MODELS_BIN 和 APSIM_ROOT。
                </p>
              </div>
            )}

            {error && <p role="alert" className="mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs leading-5 text-red-700">{error}</p>}

            <button
              type="submit"
              disabled={running}
              className="mt-5 flex w-full items-center justify-center gap-2 rounded-xl bg-stone-800 px-4 py-3 text-sm font-medium text-white transition hover:bg-stone-900 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {running ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
              {running ? '正在运行 APSIM…' : '估计产量并生成报告'}
            </button>
          </form>

          <section className="min-w-0">
            {!result && !running && (
              <div className="grid min-h-[560px] place-items-center rounded-2xl border border-dashed border-stone-300 bg-white/60 p-8 text-center">
                <div>
                  <span className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-emerald-100 text-emerald-700"><BarChart3 size={26} /></span>
                  <h2 className="mt-4 text-base font-semibold text-stone-700">等待生成产量报告</h2>
                  <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-stone-500">报告会在这里直接预览，并提供独立打开入口。</p>
                </div>
              </div>
            )}
            {running && (
              <div aria-live="polite" className="grid min-h-[560px] place-items-center rounded-2xl border border-stone-200 bg-white p-8 text-center">
                <div>
                  <Loader2 size={32} className="mx-auto animate-spin text-emerald-600" />
                  <h2 className="mt-4 text-base font-semibold text-stone-700">APSIM 正在计算</h2>
                  <p className="mt-2 text-sm text-stone-500">正在读取生长时序并生成交互式报告…</p>
                </div>
              </div>
            )}
            {result && reportUrl && (
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                  <Metric icon={<BarChart3 size={16} />} label="估算产量" value={result.metrics.estimated_yield_t_ha.toFixed(3)} unit="t/ha" />
                  <Metric icon={<Leaf size={16} />} label="峰值 LAI" value={result.metrics.peak_lai.toFixed(3)} unit="m²/m²" />
                  <Metric icon={<Activity size={16} />} label="最大生物量" value={result.metrics.max_biomass_g_m2.toFixed(0)} unit="g/m²" />
                  <Metric icon={<CalendarDays size={16} />} label="有效天数" value={String(result.metrics.simulation_days)} unit="天" />
                </div>
                <div className="overflow-hidden rounded-2xl border border-stone-200 bg-white shadow-sm">
                  <div className="flex items-center justify-between gap-3 border-b border-stone-200 px-4 py-3">
                    <div className="min-w-0">
                      <p className="flex items-center gap-2 text-sm font-medium text-stone-800"><FileText size={15} />{result.artifact.title}</p>
                      <p className="mt-1 truncate text-xs text-stone-500">{result.summary}</p>
                    </div>
                    <a href={reportUrl} target="_blank" rel="noreferrer" className="flex shrink-0 items-center gap-1.5 rounded-lg border border-stone-200 px-3 py-2 text-xs font-medium text-stone-700 hover:bg-stone-50">
                      <ExternalLink size={13} />独立打开
                    </a>
                  </div>
                  <iframe title="APSIM 产量估计报告" src={reportUrl} className="h-[680px] w-full bg-[#0f1117]" />
                </div>
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  )
}

const inputClass = 'w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm text-stone-700 outline-none transition focus:border-stone-400'

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="block"><span className="mb-1.5 block text-xs font-medium text-stone-600">{label}</span>{children}</label>
}

function ModeButton({ active, icon, title, description, onClick }: { active: boolean; icon: React.ReactNode; title: string; description: string; onClick: () => void }) {
  return <button type="button" aria-pressed={active} onClick={onClick} className={`rounded-xl border p-3 text-left transition ${active ? 'border-emerald-400 bg-emerald-50 text-emerald-900' : 'border-stone-200 text-stone-500 hover:bg-stone-50'}`}><span className="flex items-center gap-2 text-xs font-semibold">{icon}{title}</span><span className="mt-1 block text-[10px] opacity-70">{description}</span></button>
}

function Metric({ icon, label, value, unit }: { icon: React.ReactNode; label: string; value: string; unit: string }) {
  return <div className="rounded-xl border border-stone-200 bg-white p-4 shadow-sm"><div className="flex items-center gap-2 text-xs text-stone-500">{icon}{label}</div><div className="mt-2 text-xl font-semibold tabular-nums text-stone-800">{value}<span className="ml-1 text-xs font-normal text-stone-400">{unit}</span></div></div>
}
