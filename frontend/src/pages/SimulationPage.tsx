import { AlertTriangle, Footprints, Save, Siren, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { IntersectionMap } from '../components/IntersectionMap'
import { Panel, SimBadge, Waiting } from '../components/Panel'
import { SignalHead } from '../components/SignalHead'
import { Field, PageGrid } from '../components/ui'
import { useLiveData } from '../hooks/useLiveData'
import { APPROACH_LABEL, clockSec, secs } from '../lib/format'
import { api } from '../services/api'
import type { Approach } from '../types/traffic'
import { APPROACHES } from '../types/traffic'

interface Timing {
  min_green_s: number
  max_green_s: number
  yellow_s: number
  clearance_s: number
  preempt_min_green_s: number
  starvation_s: number
  max_skip_s: number
}

export function SimulationPage() {
  const { snapshot } = useLiveData()
  const [timing, setTiming] = useState<Timing | null>(null)
  const [rates, setRates] = useState<Record<Approach, number> | null>(null)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [pre, setPre] = useState<{ approach: Approach; hold_s: number; reason: string }>({ approach: 'north', hold_s: 20, reason: 'Emergency vehicle' })
  const box = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ w: 600, h: 420 })

  useEffect(() => {
    if (!box.current) return
    const ro = new ResizeObserver(([e]) => setSize({ w: e.contentRect.width, h: e.contentRect.height }))
    ro.observe(box.current)
    return () => ro.disconnect()
  }, [])

  useEffect(() => {
    api.get<{ config: { starvation_s: number; max_skip_s: number } }>('/api/priority').then((p) =>
      api.get<{ config: Omit<Timing, 'starvation_s' | 'max_skip_s'> }>('/api/simulation/state').then((s) =>
        setTiming({ ...s.config, starvation_s: p.config.starvation_s, max_skip_s: p.config.max_skip_s }),
      ),
    ).catch(() => undefined)
  }, [])
  useEffect(() => {
    if (snapshot?.demo && !rates) setRates(snapshot.demo.rates_vpm)
  }, [snapshot, rates])

  if (!snapshot) return <Waiting />
  const sig = snapshot.signal

  const saveTiming = () =>
    timing &&
    api
      .post('/api/simulation/config', timing)
      .then(() => setMsg({ ok: true, text: 'Timing applied to the running simulation.' }))
      .catch((e: Error) => setMsg({ ok: false, text: e.message }))
  const setRate = (a: Approach, v: number) => {
    setRates((r) => (r ? { ...r, [a]: v } : r))
    api.post('/api/simulation/demand', { approach: a, rate_vpm: v }).catch((e: Error) => setMsg({ ok: false, text: e.message }))
  }
  const preempt = () =>
    api.post('/api/simulation/preempt', pre).then(() => setMsg({ ok: true, text: `Pre-emption requested for ${APPROACH_LABEL[pre.approach]}.` })).catch((e: Error) => setMsg({ ok: false, text: e.message }))
  const cancelPreempt = () => api.del('/api/simulation/preempt').catch(() => undefined)
  const ped = (a: Approach) => api.post('/api/simulation/pedestrian', { approach: a }).catch(() => undefined)
  const numIn = (k: keyof Timing, label: string, step = 1) => (
    <Field label={label}>
      <input type="number" step={step} className="input num" value={timing?.[k] ?? ''} onChange={(e) => setTiming((t) => (t ? { ...t, [k]: Number(e.target.value) } : t))} />
    </Field>
  )

  return (
    <PageGrid className="grid gap-3 xl:grid-cols-[1.5fr_1fr]">
      <div className="flex flex-col gap-3">
        <div className="flex items-start gap-2 border border-warn/50 bg-warn/5 px-3 py-2 text-[11px] text-warn">
          <AlertTriangle size={14} className="mt-px shrink-0" />
          Research simulation only. This software has no connection to any real traffic-signal controller and must not be connected to one.
        </div>
        <Panel title={<>Simulated Intersection <SimBadge /></>} className="h-[460px]">
          <div ref={box} className="relative h-full w-full overflow-hidden">
            {(() => {
              const sc = Math.max(0.5, Math.min(1, size.h / 560))
              return <IntersectionMap snapshot={snapshot} showQueues scale={sc} cx={size.w / 2} cy={size.h / 2} extent={{ v: size.h / 2 / sc, h: size.w / 2 / sc }} />
            })()}
            <div className="absolute left-3 top-3 space-y-1 bg-ink-950/85 p-2 text-[11px]">
              <div className="num text-white">
                {APPROACH_LABEL[sig.current]} · {sig.stage.replace('_', '-').toUpperCase()} · {sig.stage_elapsed_s.toFixed(0)}s
              </div>
              {sig.stage === 'green' && (
                <div className="num text-txt-dim">
                  min-green left {sig.remaining_min_green_s.toFixed(0)}s · max-green left {sig.remaining_max_green_s.toFixed(0)}s
                </div>
              )}
              {sig.target && <div className="num text-warn">→ switching to {APPROACH_LABEL[sig.target]}</div>}
            </div>
          </div>
        </Panel>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {APPROACHES.map((a) => {
            const st = snapshot.approaches[a]
            return (
              <div key={a} className={`panel p-3 ${sig.colours[a] === 'green' ? 'border-ok' : ''}`}>
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-white">{APPROACH_LABEL[a]}</span>
                  <SignalHead colour={sig.colours[a]} size={8} horizontal />
                </div>
                <div className="num mt-2 grid grid-cols-2 gap-1 text-[11px] text-txt-dim">
                  <span>Queue <b className="text-num">{st.measurement.queue_count}</b></span>
                  <span>Score <b className="text-num">{st.congestion.score.toFixed(0)}</b></span>
                  <span>Unserved <b className="text-white">{secs(sig.time_since_served_s[a])}</b></span>
                  <span>Green total <b className="text-white">{secs(sig.served_seconds[a])}</b></span>
                </div>
                <button className="btn mt-2 w-full justify-center py-0.5 text-[11px]" onClick={() => ped(a)} disabled={st.measurement.pedestrian_request}>
                  <Footprints size={11} /> {st.measurement.pedestrian_request ? 'Pedestrian call pending' : 'Pedestrian call'}
                </button>
              </div>
            )
          })}
        </div>
      </div>

      <div className="flex flex-col gap-3">
        <Panel title="Signal Phase Constraints" bodyClassName="p-3 space-y-3">
          {timing ? (
            <>
              <div className="grid grid-cols-2 gap-3">
                {numIn('min_green_s', 'Min green (s)')}
                {numIn('max_green_s', 'Max green (s)')}
                {numIn('yellow_s', 'Yellow (s)', 0.5)}
                {numIn('clearance_s', 'All-red clearance (s)', 0.5)}
                {numIn('preempt_min_green_s', 'Pre-emption min green (s)')}
                {numIn('starvation_s', 'Starvation limit (s)')}
                {numIn('max_skip_s', 'Max skip of empty approach (s)')}
              </div>
              <button className="btn btn-primary" onClick={saveTiming}>
                <Save size={12} /> Apply
              </button>
              {msg && <div className={`text-[12px] ${msg.ok ? 'text-ok' : 'text-crit'}`}>{msg.text}</div>}
              <p className="text-[10px] leading-relaxed text-txt-mute">
                Phasing: strict split phasing — one approach green at a time; every tick the engine asserts that no conflicting approaches are non-red.
                A green is held while its queue discharges and ends when the queue clears, at max green, or by the fairness rule; the next green goes to the
                highest-priority approach.
              </p>
            </>
          ) : (
            <Waiting />
          )}
        </Panel>
        <Panel title={<><Siren size={13} className="text-crit" /> Emergency Pre-emption (simulated)</>} bodyClassName="p-3 space-y-2">
          {sig.preemption ? (
            <div className="flex items-center gap-2 border border-crit/60 bg-crit/10 px-2 py-1.5 text-[12px]">
              <Siren size={14} className="text-crit" />
              <span className="flex-1 text-white">
                {sig.preemption.reason} — {APPROACH_LABEL[sig.preemption.approach]}{' '}
                {sig.preemption.active_since === null ? '(ending current green safely…)' : `(holding green ${sig.preemption.hold_s.toFixed(0)} s)`}
              </span>
              <button className="btn py-0.5" onClick={cancelPreempt}><X size={11} /> Cancel</button>
            </div>
          ) : (
            <div className="grid grid-cols-3 gap-2">
              <Field label="Approach">
                <select className="input" value={pre.approach} onChange={(e) => setPre({ ...pre, approach: e.target.value as Approach })}>
                  {APPROACHES.map((a) => <option key={a} value={a}>{APPROACH_LABEL[a]}</option>)}
                </select>
              </Field>
              <Field label="Hold green (s)">
                <input type="number" min={5} max={120} className="input num" value={pre.hold_s} onChange={(e) => setPre({ ...pre, hold_s: Number(e.target.value) })} />
              </Field>
              <Field label="Reason">
                <input className="input" value={pre.reason} onChange={(e) => setPre({ ...pre, reason: e.target.value })} />
              </Field>
            </div>
          )}
          {!sig.preemption && (
            <button className="btn border-crit/70 text-crit hover:bg-crit/10" onClick={preempt}><Siren size={12} /> Request pre-emption</button>
          )}
          <p className="text-[10px] leading-relaxed text-txt-mute">
            The current green ends after at least the pre-emption minimum green, always through yellow and all-red; the requested approach then stays green
            for the hold time. Simulation only — no output to real signals.
          </p>
        </Panel>
        {snapshot.demo && rates && (
          <Panel title={<>Demo Demand <SimBadge label="Demo source" /></>} bodyClassName="p-3 space-y-2">
            <p className="text-[11px] text-txt-dim">Arrival rate fed into the demo traffic model (used only for approaches without camera data). Change it to watch the priority engine respond.</p>
            {APPROACHES.map((a) => (
              <div key={a} className="flex items-center gap-2 text-[12px]">
                <span className="w-12">{APPROACH_LABEL[a]}</span>
                <input type="range" min={0} max={30} step={0.5} value={rates[a]} onChange={(e) => setRate(a, Number(e.target.value))} className="flex-1 accent-sky-400" />
                <span className="num w-20 text-right text-white">{rates[a].toFixed(1)} veh/min</span>
              </div>
            ))}
          </Panel>
        )}
        <Panel title="Simulation Events" className="min-h-[220px] flex-1" bodyClassName="overflow-auto">
          <ul className="text-[11px]">
            {sig.events.map((e, i) => (
              <li key={i} className="flex gap-2 border-b border-line-soft/50 px-3 py-1.5">
                <span className="num shrink-0 text-txt-mute">{clockSec(e.ts)}</span>
                <span className={`shrink-0 uppercase ${e.kind === 'phase_start' ? 'text-ok' : e.kind === 'yellow' ? 'text-warn' : 'text-crit'}`}>{e.kind.replace('_', ' ')}</span>
                <span className="text-txt">{e.reason}</span>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </PageGrid>
  )
}
