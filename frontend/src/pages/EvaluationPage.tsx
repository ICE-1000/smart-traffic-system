import { RotateCcw, Save } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Panel, Waiting } from '../components/Panel'
import { Field, PageGrid } from '../components/ui'
import { useLiveData } from '../hooks/useLiveData'
import { APPROACH_LABEL, clock, secs } from '../lib/format'
import { CHART } from '../lib/series'
import { api } from '../services/api'
import type { Approach } from '../types/traffic'
import { APPROACHES } from '../types/traffic'

interface Side {
  arrived: number
  departed: number
  throughput_vph: number
  mean_delay_s: number
  vehicle_hours_delay: number
  queued_now: number
  max_queue: Record<Approach, number>
  stop_rate: number
  per_approach_mean_delay_s: Record<Approach, number>
}
interface Evaluation {
  site: { name: string; node_type: string }
  run_started: number
  elapsed_s: number
  warming_up: boolean
  inputs: Record<Approach, { rate_vpm: number; heavy_share: number; source: string }>
  adaptive: Side
  fixed: Side
  improvement_pct: Record<string, number | null>
  fixed_plan: { order: Approach[]; green_s: Record<Approach, number>; cycle_s: number }
  saturation_vps: number
  series: { t: number; adaptive_delay: number; fixed_delay: number; adaptive_queue: number; fixed_queue: number }[]
}
interface Run {
  run_started: number
  saved: number
  elapsed_s: number
  sources: string
  adaptive_mean_delay_s: number
  fixed_mean_delay_s: number
  adaptive_vehicle_hours: number
  fixed_vehicle_hours: number
  improvement_pct: Record<string, number | null>
}

const ADAPTIVE = '#3cc4ff'
const FIXED = '#ff8a3d'

function Pct({ v }: { v: number | null | undefined }) {
  if (v === null || v === undefined) return <span className="text-txt-mute">—</span>
  const good = v > 0
  return (
    <span className={`num font-semibold ${good ? 'text-ok' : v < 0 ? 'text-crit' : 'text-txt-dim'}`}>
      {v > 0 ? '▼' : v < 0 ? '▲' : ''} {Math.abs(v).toFixed(1)}%
    </span>
  )
}

function Compare({ title, unit, a, f, pct, higherIsBetter = false, fmt = (x: number) => x.toFixed(1) }: {
  title: string
  unit: string
  a: number
  f: number
  pct: number | null | undefined
  higherIsBetter?: boolean
  fmt?: (x: number) => string
}) {
  return (
    <div className="panel panel-corners px-3 pb-2.5 pt-1.5">
      <div className="stat-title">{title}</div>
      <div className="mt-2 grid grid-cols-2 gap-2">
        <div>
          <div className="text-[10px] uppercase tracking-wider" style={{ color: ADAPTIVE }}>Adaptive</div>
          <div className="num text-[22px] leading-tight text-white">{fmt(a)}<span className="ml-1 text-[11px] text-txt-dim">{unit}</span></div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-wider" style={{ color: FIXED }}>Fixed-time</div>
          <div className="num text-[22px] leading-tight text-txt">{fmt(f)}<span className="ml-1 text-[11px] text-txt-dim">{unit}</span></div>
        </div>
      </div>
      <div className="mt-1 text-[11px] text-txt-dim">
        {higherIsBetter ? (
          pct === null || pct === undefined ? '—' : <span className={`num font-semibold ${pct > 0 ? 'text-ok' : pct < 0 ? 'text-crit' : ''}`}>{pct > 0 ? '▲' : pct < 0 ? '▼' : ''} {Math.abs(pct).toFixed(1)}% vs fixed</span>
        ) : (
          <>
            <Pct v={pct} /> {pct !== null && pct !== undefined && (pct >= 0 ? 'reduction vs fixed' : 'increase vs fixed')}
          </>
        )}
      </div>
    </div>
  )
}

export function EvaluationPage() {
  const { snapshot } = useLiveData()
  const [ev, setEv] = useState<Evaluation | null>(null)
  const [runs, setRuns] = useState<Run[]>([])
  const [green, setGreen] = useState<Record<string, number> | null>(null)
  const [sat, setSat] = useState<number | null>(null)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)

  const load = useCallback(() => {
    api.get<Evaluation>('/api/evaluation').then((e) => {
      setEv(e)
      setGreen((g) => g ?? e.fixed_plan.green_s)
      setSat((x) => x ?? e.saturation_vps)
    }).catch(() => undefined)
    api.get<Run[]>('/api/evaluation/runs').then(setRuns).catch(() => undefined)
  }, [])
  useEffect(() => {
    load()
    const t = window.setInterval(load, 5000)
    return () => window.clearInterval(t)
  }, [load])

  if (!ev || !snapshot) return <Waiting />
  const a = ev.adaptive
  const f = ev.fixed
  const imp = ev.improvement_pct
  const perApproach = APPROACHES.map((x) => ({ name: APPROACH_LABEL[x], adaptive: a.per_approach_mean_delay_s[x], fixed: f.per_approach_mean_delay_s[x] }))
  const roundabout = ev.site.node_type === 'roundabout'

  const save = () =>
    api
      .post('/api/evaluation/config', { green_s: green, saturation_vps: sat })
      .then(() => {
        setMsg({ ok: true, text: 'Saved — a new comparison run has started.' })
        load()
      })
      .catch((e: Error) => setMsg({ ok: false, text: e.message }))
  const reset = () => api.post('/api/evaluation/reset', {}).then(() => { setMsg({ ok: true, text: 'New comparison run started.' }); load() })

  return (
    <PageGrid className="space-y-3">
      <div className="flex flex-wrap items-start gap-3 border border-line-soft bg-ink-900/80 px-3 py-2 text-[11px] leading-relaxed text-txt-dim">
        <div className="min-w-0 flex-1">
          <span className="font-semibold text-white">Adaptive vs fixed-time — counterfactual comparison.</span> The same arrivals (from each approach's
          measured arrival rate) feed two identical queue models of {ev.site.name}: one run by this system's adaptive controller, one by a
          conventional fixed-time plan. Differences are caused by the signal plan alone. Model estimates for decision support — not what the
          real signals did.
          {roundabout && <span className="text-warn"> This site is a roundabout: results describe a hypothetical signalised operation.</span>}
        </div>
        <div className="num shrink-0 text-right">
          <div className="text-white">Run time {secs(ev.elapsed_s)}</div>
          <div>started {clock(ev.run_started)}</div>
          {ev.warming_up && <div className="text-warn">warming up — read results after 10 min</div>}
        </div>
        <button className="btn shrink-0" onClick={reset}>
          <RotateCcw size={12} /> New run
        </button>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Compare title="Mean delay per vehicle" unit="s" a={a.mean_delay_s} f={f.mean_delay_s} pct={imp.mean_delay} />
        <Compare title="Total delay (incl. still queued)" unit="veh·h" a={a.vehicle_hours_delay} f={f.vehicle_hours_delay} pct={imp.vehicle_hours_delay} fmt={(x) => x.toFixed(2)} />
        <Compare title="Throughput" unit="veh/h" a={a.throughput_vph} f={f.throughput_vph} pct={imp.throughput} higherIsBetter fmt={(x) => x.toFixed(0)} />
        <Compare title="Vehicles that had to stop" unit="%" a={a.stop_rate * 100} f={f.stop_rate * 100} pct={imp.stop_rate} fmt={(x) => x.toFixed(0)} />
      </div>

      <div className="grid gap-3 xl:grid-cols-[1.5fr_1fr]">
        <Panel title="Mean Delay Over the Run" className="h-[280px]" bodyClassName="p-2">
          {ev.series.length < 2 ? (
            <Waiting text="Collecting data…" />
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={ev.series} margin={{ top: 4, right: 8, left: -14, bottom: 0 }}>
                <CartesianGrid stroke={CHART.grid} strokeDasharray="2 4" vertical={false} />
                <XAxis dataKey="t" tickFormatter={(v) => `${Math.floor(v / 60)}:${String(Math.round(v % 60)).padStart(2, '0')}`} tick={CHART.tick} stroke={CHART.axis} minTickGap={30} />
                <YAxis tick={CHART.tick} stroke={CHART.axis} unit="s" width={50} />
                <Tooltip {...CHART.tooltip} labelFormatter={(v) => `after ${secs(Number(v))}`} />
                <Legend iconSize={8} wrapperStyle={{ fontSize: 10 }} verticalAlign="top" align="right" />
                <Line dataKey="adaptive_delay" name="Adaptive (cumulative mean)" stroke={ADAPTIVE} dot={false} strokeWidth={1.8} isAnimationActive={false} />
                <Line dataKey="fixed_delay" name="Fixed-time (cumulative mean)" stroke={FIXED} dot={false} strokeWidth={1.8} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </Panel>
        <Panel title="Mean Delay by Approach" className="h-[280px]" bodyClassName="p-2">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={perApproach} margin={{ top: 4, right: 8, left: -14, bottom: 0 }}>
              <CartesianGrid stroke={CHART.grid} strokeDasharray="2 4" vertical={false} />
              <XAxis dataKey="name" tick={CHART.tick} stroke={CHART.axis} />
              <YAxis tick={CHART.tick} stroke={CHART.axis} unit="s" width={50} />
              <Tooltip {...CHART.tooltip} />
              <Legend iconSize={8} wrapperStyle={{ fontSize: 10 }} verticalAlign="top" align="right" />
              <Bar dataKey="adaptive" name="Adaptive" fill={ADAPTIVE} isAnimationActive={false} />
              <Bar dataKey="fixed" name="Fixed-time" fill={FIXED} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </Panel>
      </div>

      <div className="grid items-start gap-3 xl:grid-cols-2">
        <Panel title="Inputs (shared by both plans)" bodyClassName="p-3">
          <table className="w-full text-[11px]">
            <thead className="text-txt-dim">
              <tr>
                <th className="py-1 text-left font-normal">Approach</th>
                <th className="text-right font-normal">Arrivals</th>
                <th className="text-right font-normal">Heavy</th>
                <th className="text-right font-normal">Source</th>
              </tr>
            </thead>
            <tbody>
              {APPROACHES.map((x) => {
                const i = ev.inputs[x]
                return (
                  <tr key={x} className="border-t border-line-soft/60">
                    <td className="py-1">{APPROACH_LABEL[x]}</td>
                    <td className="num text-right">{i ? `${(i.rate_vpm * 60).toFixed(0)} veh/h` : '—'}</td>
                    <td className="num text-right">{i ? `${(i.heavy_share * 100).toFixed(0)}%` : '—'}</td>
                    <td className={`text-right text-[10px] font-semibold ${i?.source === 'vision' ? 'text-ok' : i?.source === 'demo' ? 'text-warn' : 'text-txt-mute'}`}>
                      {i ? (i.source === 'vision' ? 'AI' : i.source === 'demo' ? 'SIM' : 'NO DATA') : '—'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          <div className="num mt-3 grid grid-cols-2 gap-2 text-[11px] text-txt-dim">
            <span>Arrived <b className="text-white">{a.arrived}</b></span>
            <span>Departed A/F <b className="text-white">{a.departed}/{f.departed}</b></span>
            <span>Queued now A/F <b className="text-white">{a.queued_now}/{f.queued_now}</b></span>
            <span>Stop rate A/F <b className="text-white">{(a.stop_rate * 100).toFixed(0)}%/{(f.stop_rate * 100).toFixed(0)}%</b></span>
          </div>
        </Panel>

        <Panel title="Fixed-time Plan & Model" bodyClassName="p-3 space-y-3">
          {green && sat !== null ? (
            <>
              <div className="grid grid-cols-4 gap-2">
                {ev.fixed_plan.order.map((x) => (
                  <Field key={x} label={`${APPROACH_LABEL[x]} green`}>
                    <input type="number" min={5} max={180} className="input num" value={green[x]} onChange={(e) => setGreen({ ...green, [x]: Number(e.target.value) })} />
                  </Field>
                ))}
              </div>
              <div className="num text-[11px] text-txt-dim">
                Order {ev.fixed_plan.order.map((x) => APPROACH_LABEL[x][0]).join(' → ')} · cycle {ev.fixed_plan.cycle_s.toFixed(0)} s (greens + yellow + all-red, from Signal Simulation)
              </div>
              <Field label="Saturation flow per approach (veh/s)">
                <input type="number" step={0.05} min={0.2} max={1} className="input num" value={sat} onChange={(e) => setSat(Number(e.target.value))} />
              </Field>
              <p className="text-[10px] leading-relaxed text-txt-mute">
                For field evaluation, enter the real signal timings measured on site (stopwatch the cycle) so the fixed-time plan represents the existing schedule.
              </p>
              <button className="btn btn-primary" onClick={save}>
                <Save size={12} /> Save & start new run
              </button>
              {msg && <div className={`text-[12px] ${msg.ok ? 'text-ok' : 'text-crit'}`}>{msg.text}</div>}
            </>
          ) : (
            <Waiting />
          )}
        </Panel>
      </div>

      <Panel title="Saved Comparison Runs (this site)" bodyClassName="overflow-auto">
        <table className="w-full text-[12px]">
          <thead className="text-[11px] uppercase tracking-wider text-txt-dim">
            <tr>
              {['Started', 'Length', 'Inputs', 'Mean delay A / F', 'Total delay A / F', 'Delay change', 'Throughput change'].map((h) => (
                <th key={h} className="px-3 py-2 text-left font-normal">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {runs.map((r) => (
              <tr key={r.run_started} className="border-t border-line-soft/60">
                <td className="num px-3 py-1.5">{new Date(r.run_started * 1000).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' })}</td>
                <td className="num px-3">{secs(r.elapsed_s)}</td>
                <td className="px-3 text-txt-dim">{r.sources}</td>
                <td className="num px-3">{r.adaptive_mean_delay_s} s / {r.fixed_mean_delay_s} s</td>
                <td className="num px-3">{r.adaptive_vehicle_hours} / {r.fixed_vehicle_hours} veh·h</td>
                <td className="px-3"><Pct v={r.improvement_pct.mean_delay} /></td>
                <td className="num px-3">{r.improvement_pct.throughput !== null && r.improvement_pct.throughput !== undefined ? <span className={r.improvement_pct.throughput >= 0 ? 'text-ok' : 'text-crit'}>{r.improvement_pct.throughput > 0 ? '+' : ''}{r.improvement_pct.throughput}%</span> : '—'}</td>
              </tr>
            ))}
            {runs.length === 0 && (
              <tr><td colSpan={7} className="p-3 text-txt-dim">Runs are saved every minute after the first minute.</td></tr>
            )}
          </tbody>
        </table>
      </Panel>
    </PageGrid>
  )
}
