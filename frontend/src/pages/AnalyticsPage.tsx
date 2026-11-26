import { Download, RefreshCw } from 'lucide-react'
import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Panel, Waiting } from '../components/Panel'
import { PageGrid } from '../components/ui'
import { APPROACH_COLOUR, APPROACH_LABEL, clock } from '../lib/format'
import { CHART } from '../lib/series'
import { api } from '../services/api'
import { APPROACHES } from '../types/traffic'

interface History {
  sources: string[]
  bucket_s: number
  buckets: Record<string, number>[]
}
const RANGES = [
  { label: '15 min', minutes: 15, bucket: 15 },
  { label: '1 hour', minutes: 60, bucket: 60 },
  { label: '6 hours', minutes: 360, bucket: 300 },
  { label: '24 hours', minutes: 1440, bucket: 900 },
  { label: '7 days', minutes: 10080, bucket: 3600 },
  { label: '30 days', minutes: 43200, bucket: 14400 },
]

const fmtTick = (minutes: number) => (v: number) =>
  minutes > 1440
    ? new Date(v * 1000).toLocaleString([], { day: '2-digit', month: 'short', hour: '2-digit', hour12: false })
    : clock(v)

/** Historical charts from the database (/api/traffic/history). */
export function AnalyticsPage() {
  const [range, setRange] = useState(RANGES[0])
  const [data, setData] = useState<History | null>(null)
  const [err, setErr] = useState<string | null>(null)

  const load = useCallback(() => {
    api
      .get<History>(`/api/traffic/history?minutes=${range.minutes}&bucket_s=${range.bucket}`)
      .then((d) => {
        setData(d)
        setErr(null)
      })
      .catch((e: Error) => setErr(e.message))
  }, [range])

  useEffect(() => {
    load()
    const t = window.setInterval(load, 15000)
    return () => window.clearInterval(t)
  }, [load])

  const rows = (data?.buckets ?? []).map((b) => ({
    ...b,
    ...Object.fromEntries(APPROACHES.map((a) => [`${a}_green_pct`, Math.round((b[`${a}_green`] ?? 0) * 100)])),
  }))
  const tick = fmtTick(range.minutes)
  const simulated = data?.sources.includes('demo')
  const measured = data?.sources.includes('vision')

  const chart = (title: string, body: ReactNode, cls = '') => (
    <Panel title={title} className={`h-[290px] ${cls}`} bodyClassName="p-2">
      {rows.length < 2 ? <Waiting text={err ?? 'Not enough stored data yet for this range — measurements are saved every 5 s.'} /> : <ResponsiveContainer width="100%" height="100%">{body as never}</ResponsiveContainer>}
    </Panel>
  )
  const axes = (
    <>
      <CartesianGrid stroke={CHART.grid} strokeDasharray="2 4" vertical={false} />
      <XAxis dataKey="ts" tickFormatter={tick} tick={CHART.tick} stroke={CHART.axis} minTickGap={30} />
      <Tooltip {...CHART.tooltip} labelFormatter={(v) => tick(Number(v))} />
      <Legend iconSize={8} wrapperStyle={{ fontSize: 10 }} verticalAlign="top" align="right" />
    </>
  )
  const perApproach = (suffix: string) =>
    APPROACHES.map((a) => <Line key={a} dataKey={`${a}_${suffix}`} name={APPROACH_LABEL[a]} stroke={APPROACH_COLOUR[a]} dot={false} strokeWidth={1.6} isAnimationActive={false} />)

  return (
    <PageGrid>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="mr-2 text-[12px] text-txt-dim">Time range</span>
        {RANGES.map((r) => (
          <button key={r.label} className={`tab px-3 py-1 ${r === range ? 'tab-active' : ''}`} onClick={() => setRange(r)}>
            {r.label}
          </button>
        ))}
        <button className="btn ml-2" onClick={load}>
          <RefreshCw size={12} /> Refresh
        </button>
        <a className="btn" href={`/api/traffic/history.csv?minutes=${range.minutes}&bucket_s=${range.bucket}`} download>
          <Download size={12} /> Export CSV
        </a>
        <span className="ml-auto text-[11px] text-txt-dim">
          {rows.length} buckets of {range.bucket}s
          {measured && <span className="ml-2 border border-ok/60 bg-ok/10 px-1.5 py-px text-[10px] font-semibold uppercase tracking-wider text-ok">Camera data</span>}
          {simulated && <span className="sim-badge ml-2">Contains simulated data</span>}
        </span>
      </div>
      <div className="grid gap-3 xl:grid-cols-2">
        {chart('Vehicle Count Over Time (vehicles in view)', (
          <AreaChart data={rows} margin={{ top: 4, right: 8, left: -14, bottom: 0 }}>
            {axes}
            <YAxis tick={CHART.tick} stroke={CHART.axis} />
            <Area dataKey="in_view" name="Vehicles in view" stroke="#3cc4ff" fill="#3cc4ff" fillOpacity={0.2} isAnimationActive={false} />
          </AreaChart>
        ))}
        {chart('Congestion Score by Approach', (
          <LineChart data={rows} margin={{ top: 4, right: 8, left: -14, bottom: 0 }}>
            {axes}
            <YAxis domain={[0, 100]} tick={CHART.tick} stroke={CHART.axis} />
            {perApproach('score')}
          </LineChart>
        ))}
        {chart('Average Waiting Time (s)', (
          <LineChart data={rows} margin={{ top: 4, right: 8, left: -14, bottom: 0 }}>
            {axes}
            <YAxis tick={CHART.tick} stroke={CHART.axis} />
            {perApproach('wait')}
          </LineChart>
        ))}
        {chart('Arrival and Departure Rates (veh/min, all approaches)', (
          <LineChart data={rows} margin={{ top: 4, right: 8, left: -14, bottom: 0 }}>
            {axes}
            <YAxis tick={CHART.tick} stroke={CHART.axis} />
            <Line dataKey="arrivals" name="Arrivals" stroke="#ffc23d" dot={false} strokeWidth={1.8} isAnimationActive={false} />
            <Line dataKey="departures" name="Departures" stroke="#3cc4ff" dot={false} strokeWidth={1.8} isAnimationActive={false} />
          </LineChart>
        ))}
        {chart('Congestion Index by Approach (CI = delay ÷ free-flow time)', (
          <LineChart data={rows} margin={{ top: 4, right: 8, left: -14, bottom: 0 }}>
            {axes}
            <YAxis tick={CHART.tick} stroke={CHART.axis} />
            {perApproach('ci')}
          </LineChart>
        ))}
        {chart('Mean Delay of Departed Vehicles (s)', (
          <LineChart data={rows} margin={{ top: 4, right: 8, left: -14, bottom: 0 }}>
            {axes}
            <YAxis tick={CHART.tick} stroke={CHART.axis} />
            {perApproach('delay')}
          </LineChart>
        ))}
        {chart('Historical Priority Allocation (share of simulated green, %)', (
          <BarChart data={rows} margin={{ top: 4, right: 8, left: -14, bottom: 0 }}>
            {axes}
            <YAxis domain={[0, 100]} tick={CHART.tick} stroke={CHART.axis} unit="%" />
            {APPROACHES.map((a) => (
              <Bar key={a} dataKey={`${a}_green_pct`} stackId="g" name={APPROACH_LABEL[a]} fill={APPROACH_COLOUR[a]} isAnimationActive={false} />
            ))}
          </BarChart>
        ), 'xl:col-span-2')}
      </div>
      <div className="mt-3 grid items-start gap-3 2xl:grid-cols-2">
        <PeriodPanel />
        <ForecastPanel />
      </div>
    </PageGrid>
  )
}

interface PeriodRow {
  period: string
  label: string
  approach: string
  samples: number
  minutes: number
  mean_queue: number | null
  mean_wait_s: number | null
  mean_arrival_vph: number | null
  mean_ci: number | null
  mean_delay_s: number | null
  sources: string[]
}

/** Proposal peak periods (07:00–09:00, 16:00–19:00) vs off-peak, from stored measurements. */
function PeriodPanel() {
  const [days, setDays] = useState(7)
  const [weekdays, setWeekdays] = useState(false)
  const [rows, setRows] = useState<PeriodRow[]>([])
  const [tz, setTz] = useState('')
  useEffect(() => {
    const load = () =>
      api.get<{ rows: PeriodRow[]; timezone: string }>(`/api/analytics/periods?days=${days}&weekdays_only=${weekdays}`).then((r) => {
        setRows(r.rows)
        setTz(r.timezone)
      }).catch(() => undefined)
    load()
    const t = window.setInterval(load, 30000)
    return () => window.clearInterval(t)
  }, [days, weekdays])
  const all = rows.filter((r) => r.approach === 'all')
  const short: Record<string, string> = { am_peak: 'AM peak', pm_peak: 'PM peak', off_peak: 'Off-peak', night: 'Night' }
  return (
    <Panel
      title="Peak vs Off-peak (proposal periods)"
      actions={
        <>
          {[1, 7, 31].map((d) => (
            <button key={d} className={`tab ${days === d ? 'tab-active' : ''}`} onClick={() => setDays(d)}>{d === 1 ? '24 h' : `${d} days`}</button>
          ))}
          <button className={`tab ${weekdays ? 'tab-active' : ''}`} onClick={() => setWeekdays((w) => !w)}>Weekdays</button>
        </>
      }
      bodyClassName="p-3 space-y-3"
    >
      {all.length === 0 ? (
        <Waiting text="No stored measurements in this range yet." />
      ) : (
        <>
          <div className="h-[200px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={all.map((r) => ({ ...r, name: short[r.period] }))} margin={{ top: 4, right: 8, left: -14, bottom: 0 }}>
                <CartesianGrid stroke={CHART.grid} strokeDasharray="2 4" vertical={false} />
                <XAxis dataKey="name" tick={CHART.tick} stroke={CHART.axis} />
                <YAxis yAxisId="l" tick={CHART.tick} stroke={CHART.axis} />
                <YAxis yAxisId="r" orientation="right" tick={CHART.tick} stroke={CHART.axis} width={36} />
                <Tooltip {...CHART.tooltip} />
                <Legend iconSize={8} wrapperStyle={{ fontSize: 10 }} verticalAlign="top" align="right" />
                <Bar yAxisId="l" dataKey="mean_delay_s" name="Mean delay (s)" fill="#3cc4ff" isAnimationActive={false} />
                <Bar yAxisId="r" dataKey="mean_ci" name="Mean CI" fill="#ffc23d" isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <table className="w-full text-[11px]">
            <thead className="text-txt-dim">
              <tr>{['Period', 'Approach', 'Coverage', 'Arrivals', 'Queue', 'Wait', 'Delay', 'CI', 'Data'].map((h) => <th key={h} className="py-1 pr-2 text-left font-normal">{h}</th>)}</tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.period + r.approach} className={`num border-t border-line-soft/60 ${r.approach === 'all' ? 'text-white' : 'text-txt-dim'}`}>
                  <td className="py-1 pr-2">{r.approach === 'all' ? r.label : ''}</td>
                  <td className="pr-2">{r.approach === 'all' ? 'All' : APPROACH_LABEL[r.approach as keyof typeof APPROACH_LABEL]}</td>
                  <td className="pr-2">{r.minutes} min</td>
                  <td className="pr-2">{r.mean_arrival_vph ?? '—'} veh/h</td>
                  <td className="pr-2">{r.mean_queue ?? '—'}</td>
                  <td className="pr-2">{r.mean_wait_s ?? '—'} s</td>
                  <td className="pr-2">{r.mean_delay_s ?? '—'} s</td>
                  <td className="pr-2 text-num">{r.mean_ci ?? '—'}</td>
                  <td className="text-[9px] font-semibold">
                    {r.sources.includes('vision') && <span className="text-ok">AI </span>}
                    {r.sources.includes('demo') && <span className="text-warn">SIM</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-[10px] text-txt-mute">Periods in local time ({tz}). Coverage = minutes of stored measurements per approach.</p>
        </>
      )}
    </Panel>
  )
}

interface Fc {
  method: string
  horizon_min: number
  sources: string[]
  approaches: Record<string, { history: { ts: number; vph: number }[]; forecast: { ts: number; vph: number }[]; mae_vph: number | null; enough_data: boolean }>
}

/** Short-term arrival forecast (proposal literature: predictive planning). */
function ForecastPanel() {
  const [fc, setFc] = useState<Fc | null>(null)
  const [appr, setAppr] = useState<(typeof APPROACHES)[number]>('north')
  useEffect(() => {
    const load = () => api.get<Fc>('/api/analytics/forecast?horizon=15').then(setFc).catch(() => undefined)
    load()
    const t = window.setInterval(load, 60000)
    return () => window.clearInterval(t)
  }, [])
  const a = fc?.approaches[appr]
  const data = a ? [...a.history.map((h) => ({ ts: h.ts, observed: h.vph })), ...a.forecast.map((f) => ({ ts: f.ts, forecast: f.vph }))] : []
  if (a && a.history.length && a.forecast.length) {
    const last = a.history[a.history.length - 1]
    const i = data.findIndex((d) => d.ts === last.ts)
    data[i] = { ...data[i], forecast: last.vph } as never
  }
  return (
    <Panel
      title="Short-term Arrival Forecast (15 min)"
      actions={APPROACHES.map((x) => (
        <button key={x} className={`tab ${appr === x ? 'tab-active' : ''}`} onClick={() => setAppr(x)}>{APPROACH_LABEL[x]}</button>
      ))}
      bodyClassName="p-3 space-y-2"
    >
      {!a ? (
        <Waiting />
      ) : !a.enough_data ? (
        <Waiting text="Needs at least 10 minutes of stored measurements for this approach." />
      ) : (
        <>
          <div className="h-[220px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data} margin={{ top: 4, right: 8, left: -14, bottom: 0 }}>
                <CartesianGrid stroke={CHART.grid} strokeDasharray="2 4" vertical={false} />
                <XAxis dataKey="ts" tickFormatter={clock} tick={CHART.tick} stroke={CHART.axis} minTickGap={30} />
                <YAxis tick={CHART.tick} stroke={CHART.axis} />
                <Tooltip {...CHART.tooltip} labelFormatter={(v) => clock(Number(v))} />
                <Legend iconSize={8} wrapperStyle={{ fontSize: 10 }} verticalAlign="top" align="right" />
                <Line dataKey="observed" name="Observed (veh/h)" stroke="#3cc4ff" dot={false} strokeWidth={1.6} isAnimationActive={false} />
                <Line dataKey="forecast" name="Forecast (veh/h)" stroke="#ffc23d" strokeDasharray="5 4" dot={false} strokeWidth={1.8} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="num flex flex-wrap gap-4 text-[11px] text-txt-dim">
            <span>Next 15 min ≈ <b className="text-num">{a.forecast[a.forecast.length - 1]?.vph}</b> veh/h</span>
            <span>One-step error (MAE) <b className="text-white">{a.mae_vph ?? '—'}</b> veh/h</span>
            <span>
              Data:{' '}
              {fc!.sources.includes('vision') && <span className="font-semibold text-ok">AI </span>}
              {fc!.sources.includes('demo') && <span className="font-semibold text-warn">SIM</span>}
            </span>
          </div>
          <p className="text-[10px] text-txt-mute">{fc!.method}. A baseline forecaster; a stronger model can be trained once weeks of camera data exist.</p>
        </>
      )}
    </Panel>
  )
}
