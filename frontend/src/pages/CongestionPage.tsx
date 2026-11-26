import { Save } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Panel, SimBadge, Waiting } from '../components/Panel'
import { CategoryTag, Field, PageGrid, ScoreBar } from '../components/ui'
import { useLiveData } from '../hooks/useLiveData'
import { APPROACH_LABEL, CATEGORY_COLOUR, secs } from '../lib/format'
import { api } from '../services/api'
import { APPROACHES } from '../types/traffic'

const COMPONENT_LABEL: Record<string, string> = {
  queue_count: 'Queue count',
  wait_time: 'Waiting time',
  queue_length: 'Queue length',
  arrival_rate: 'Arrival rate',
  net_growth: 'Net growth',
}
const COMPONENT_COLOUR: Record<string, string> = {
  queue_count: '#3cc4ff',
  wait_time: '#a77bff',
  queue_length: '#2ed47a',
  arrival_rate: '#ffc23d',
  net_growth: '#ff7a2e',
}
interface IndexCfg {
  free_flow_kmh: number
  default_section_m: number
  window_s: number
  min_samples: number
}
interface Cfg {
  weights: Record<string, number>
  norms: Record<string, number>
  thresholds: Record<string, number>
}

export function CongestionPage() {
  const { snapshot } = useLiveData()
  const [cfg, setCfg] = useState<Cfg | null>(null)
  const [weights, setWeights] = useState<Record<string, number>>({})
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [idx, setIdx] = useState<IndexCfg | null>(null)
  const [idxMsg, setIdxMsg] = useState<{ ok: boolean; text: string } | null>(null)

  useEffect(() => {
    api.get<{ config: Cfg }>('/api/congestion').then((r) => {
      setCfg(r.config)
      setWeights(r.config.weights)
    }).catch(() => undefined)
    api.get<{ config: IndexCfg }>('/api/indices').then((r) => setIdx(r.config)).catch(() => undefined)
  }, [])

  if (!snapshot) return <Waiting />
  const rows = APPROACHES.map((a) => snapshot.approaches[a])
  const top = rows.reduce((x, y) => (y.congestion.score > x.congestion.score ? y : x))
  const sum = Object.values(weights).reduce((a, b) => a + b, 0)

  const saveIdx = () =>
    idx &&
    api
      .post<IndexCfg>('/api/indices/config', idx)
      .then((c) => { setIdx(c); setIdxMsg({ ok: true, text: 'Index settings applied.' }) })
      .catch((e: Error) => setIdxMsg({ ok: false, text: e.message }))

  const save = () =>
    api
      .post<Cfg>('/api/congestion/config', { weights })
      .then((c) => {
        setCfg(c)
        setMsg({ ok: true, text: 'Weights applied to the live engine.' })
      })
      .catch((e: Error) => setMsg({ ok: false, text: e.message }))

  return (
    <PageGrid className="grid items-start gap-3 xl:grid-cols-[1.6fr_1fr]">
      <div className="flex flex-col gap-3">
        <Panel title={<>Approach Comparison <SimBadge /></>}>
          <table className="w-full text-[12px]">
            <thead className="text-[11px] uppercase tracking-wider text-txt-dim">
              <tr>
                {['Approach', 'Waiting', 'Queue length', 'Avg wait', 'Arr / Dep (veh/min)', 'Delay / CI', 'Congestion score', 'Category'].map((h) => (
                  <th key={h} className="px-3 py-2 text-left font-normal">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const m = r.measurement
                const isTop = r.approach === top.approach && r.congestion.score > 0
                return (
                  <tr key={r.approach} className={`border-t border-line-soft/60 ${isTop ? 'bg-crit/10' : ''}`}>
                    <td className="px-3 py-2.5 font-semibold text-white">
                      {APPROACH_LABEL[r.approach]} {isTop && <span className="ml-1 text-[10px] text-crit">▲ HIGHEST</span>}
                    </td>
                    <td className="num px-3">{m.queue_count} veh</td>
                    <td className="num px-3">{Math.round(m.queue_length_m)} m</td>
                    <td className="num px-3">{secs(m.avg_wait_s)}</td>
                    <td className="num px-3">{m.arrival_rate_vpm} / {m.departure_rate_vpm}</td>
                    <td className="num whitespace-nowrap px-3" title={`Mean delay of departed vehicles (last ${idx ? idx.window_s / 60 : 5} min) / free-flow time ${r.indices.free_flow_s ?? '—'} s over ${r.indices.section_m} m`}>
                      {r.indices.ci !== null ? <>{r.indices.mean_delay_s} s / <span className="text-num">{r.indices.ci.toFixed(2)}</span></> : <span className="text-txt-mute">{r.indices.samples}/3 samples</span>}
                    </td>
                    <td className="w-[28%] px-3">
                      <div className="flex items-center gap-2">
                        <ScoreBar value={r.congestion.score} colour={CATEGORY_COLOUR[r.congestion.category]} />
                        <span className="num w-8 text-right text-white">{r.congestion.score.toFixed(0)}</span>
                      </div>
                    </td>
                    <td className="px-3">
                      {m.source === 'none' ? <span className="text-[10px] font-semibold tracking-wider text-txt-mute">NO DATA</span> : <CategoryTag category={r.congestion.category} />}
                      {m.source === 'demo' && <span className="ml-1 text-[9px] font-semibold text-warn">SIM</span>}
                      {m.source === 'vision' && <span className="ml-1 text-[9px] font-semibold text-ok">AI</span>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </Panel>

        <Panel title="Score Breakdown (weighted points per indicator)" bodyClassName="p-3 space-y-3">
          {rows.map((r) => (
            <div key={r.approach}>
              <div className="mb-1 flex justify-between text-[11px]">
                <span className="text-white">{APPROACH_LABEL[r.approach]}</span>
                <span className="num text-txt-dim">{r.congestion.score.toFixed(1)} / 100</span>
              </div>
              <div className="flex h-3 w-full bg-ink-950/80 outline outline-1 outline-line-soft">
                {Object.entries(r.congestion.contributions).map(([k, v]) => (
                  <div key={k} title={`${COMPONENT_LABEL[k]}: ${v} pts (normalised ${r.congestion.components[k]})`} style={{ width: `${v}%`, background: COMPONENT_COLOUR[k] }} />
                ))}
              </div>
            </div>
          ))}
          <div className="flex flex-wrap gap-3 pt-1 text-[10px] text-txt-dim">
            {Object.keys(COMPONENT_LABEL).map((k) => (
              <span key={k} className="flex items-center gap-1"><span className="h-2 w-2" style={{ background: COMPONENT_COLOUR[k] }} />{COMPONENT_LABEL[k]}</span>
            ))}
          </div>
        </Panel>
      </div>

      <div className="flex flex-col gap-3">
      <Panel title="Congestion Index (proposal benchmark)" bodyClassName="p-3 space-y-3">
        <p className="text-[11px] leading-relaxed text-txt-dim">
          CI = (actual − free-flow travel time) / free-flow travel time. At an approach: CI = mean delay of departed vehicles ÷ free-flow time over the
          monitored section (camera queue-area length, else the default below). TTI = 1 + CI. The free-flow speed should come from off-peak moving-car runs
          (Field Surveys). The congestion score (0–100) is the operational measure used for priority; CI is the benchmarking measure for the report.
        </p>
        {idx ? (
          <>
            <div className="grid grid-cols-3 gap-3">
              <Field label="Free-flow speed (km/h)">
                <input type="number" className="input num" value={idx.free_flow_kmh} onChange={(e) => setIdx({ ...idx, free_flow_kmh: Number(e.target.value) })} />
              </Field>
              <Field label="Default section (m)">
                <input type="number" className="input num" value={idx.default_section_m} onChange={(e) => setIdx({ ...idx, default_section_m: Number(e.target.value) })} />
              </Field>
              <Field label="Window (s)">
                <input type="number" className="input num" value={idx.window_s} onChange={(e) => setIdx({ ...idx, window_s: Number(e.target.value) })} />
              </Field>
            </div>
            <button className="btn btn-primary" onClick={saveIdx}><Save size={12} /> Apply</button>
            {idxMsg && <div className={`text-[12px] ${idxMsg.ok ? 'text-ok' : 'text-crit'}`}>{idxMsg.text}</div>}
          </>
        ) : (
          <Waiting />
        )}
      </Panel>
      <Panel title="Scoring Model" bodyClassName="p-3 space-y-3 overflow-auto">
        <p className="text-[11px] leading-relaxed text-txt-dim">
          score = 100 × Σ wᵢ · min(xᵢ / normᵢ, 1). Weights must total 1.00. Normalisation bounds are the values at which an
          indicator saturates; see docs/ALGORITHMS.md for the assumptions.
        </p>
        {cfg ? (
          <>
            {Object.keys(COMPONENT_LABEL).map((k) => (
              <Field key={k} label={`${COMPONENT_LABEL[k]} · norm ${cfg.norms[k]}`}>
                <div className="flex items-center gap-2">
                  <input type="range" min={0} max={0.6} step={0.05} value={weights[k] ?? 0} onChange={(e) => setWeights((w) => ({ ...w, [k]: Number(e.target.value) }))} className="flex-1 accent-sky-400" />
                  <span className="num w-10 text-right text-white">{(weights[k] ?? 0).toFixed(2)}</span>
                </div>
              </Field>
            ))}
            <div className={`num text-[12px] ${Math.abs(sum - 1) < 1e-6 ? 'text-ok' : 'text-warn'}`}>Total {sum.toFixed(2)}</div>
            <button className="btn btn-primary" onClick={save} disabled={Math.abs(sum - 1) > 1e-6}>
              <Save size={12} /> Apply weights
            </button>
            {msg && <div className={`text-[12px] ${msg.ok ? 'text-ok' : 'text-crit'}`}>{msg.text}</div>}
            <div className="border-t border-line-soft pt-2 text-[11px] text-txt-dim">
              Categories: free &lt; {cfg.thresholds.free}, light &lt; {cfg.thresholds.light}, moderate &lt; {cfg.thresholds.moderate}, heavy &lt; {cfg.thresholds.heavy}, critical ≥ {cfg.thresholds.heavy}
            </div>
          </>
        ) : (
          <Waiting />
        )}
      </Panel>
      </div>
    </PageGrid>
  )
}
