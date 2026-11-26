import { AlertTriangle, Check, Save } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Panel, Waiting } from '../components/Panel'
import { Field, PageGrid } from '../components/ui'
import { useLiveData } from '../hooks/useLiveData'
import { APPROACH_LABEL, clockSec, secs } from '../lib/format'
import { api } from '../services/api'
import type { Incident } from '../types/traffic'

interface HistoryRow {
  id: number
  kind: Incident['kind']
  approach: Incident['approach']
  severity: Incident['severity']
  started: number
  ended: number | null
  message: string
  acknowledged: boolean
  source: string
}
type Cfg = Record<string, number>

export const INCIDENT_LABEL: Record<Incident['kind'], string> = {
  blocked_discharge: 'Blocked discharge',
  stalled_vehicle: 'Stalled vehicle',
  spillback: 'Queue spillback',
  camera_failure: 'Camera failure',
}
const CFG_FIELDS: { k: string; label: string }[] = [
  { k: 'blocked_green_s', label: 'Blocked: green time before checking (s)' },
  { k: 'blocked_window_s', label: 'Blocked: no departure for (s)' },
  { k: 'blocked_min_queue', label: 'Blocked: minimum queue (veh)' },
  { k: 'stall_s', label: 'Stalled vehicle: stationary for (s)' },
  { k: 'spillback_limit_m', label: 'Spillback: queue length (m)' },
  { k: 'camera_offline_s', label: 'Camera failure: offline for (s)' },
  { k: 'confirm_s', label: 'Confirm condition for (s)' },
  { k: 'clear_s', label: 'Clear after normal for (s)' },
]

export function IncidentsPage() {
  const { snapshot } = useLiveData()
  const [history, setHistory] = useState<HistoryRow[]>([])
  const [cfg, setCfg] = useState<Cfg | null>(null)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)

  const load = useCallback(() => {
    api.get<{ history: HistoryRow[]; config: Cfg }>('/api/incidents?status=all&limit=200').then((r) => {
      setHistory(r.history)
      setCfg((c) => c ?? r.config)
    }).catch(() => undefined)
  }, [])
  useEffect(() => {
    load()
    const t = window.setInterval(load, 5000)
    return () => window.clearInterval(t)
  }, [load])

  if (!snapshot) return <Waiting />
  const active = snapshot.incidents
  const ack = (id: number | null) => id && api.post(`/api/incidents/${id}/acknowledge`, {}).then(load)
  const saveCfg = () =>
    cfg && api.post<Cfg>('/api/incidents/config', cfg).then((c) => { setCfg(c); setMsg({ ok: true, text: 'Thresholds applied.' }) }).catch((e: Error) => setMsg({ ok: false, text: e.message }))

  return (
    <PageGrid className="grid items-start gap-3 xl:grid-cols-[1.6fr_1fr]">
      <div className="flex flex-col gap-3">
        <Panel title={`Active Incidents · ${snapshot.site.name}`} bodyClassName="p-3 space-y-2">
          {active.length === 0 && <div className="flex items-center gap-2 text-[12px] text-ok"><Check size={14} /> No active incidents.</div>}
          {active.map((i) => (
            <div key={i.key} className={`flex items-start gap-3 border px-3 py-2 ${i.severity === 'critical' ? 'border-crit/70 bg-crit/10' : 'border-warn/60 bg-warn/10'}`}>
              <AlertTriangle size={16} className={`mt-0.5 shrink-0 ${i.severity === 'critical' ? 'text-crit' : 'text-warn'}`} />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2 text-[12px]">
                  <span className="font-semibold text-white">{INCIDENT_LABEL[i.kind]}</span>
                  {i.approach && <span className="text-txt-dim">{APPROACH_LABEL[i.approach]} approach</span>}
                  <span className="num ml-auto text-txt-mute">since {clockSec(i.started)} · {secs(snapshot.ts - i.started)}</span>
                </div>
                <p className="text-[12px] text-txt">{i.message}</p>
              </div>
              {!i.acknowledged && i.db_id && (
                <button className="btn shrink-0 py-0.5" onClick={() => ack(i.db_id)}>Acknowledge</button>
              )}
              {i.acknowledged && <span className="shrink-0 text-[10px] text-txt-mute">acknowledged</span>}
            </div>
          ))}
          <p className="text-[10px] leading-relaxed text-txt-mute">
            Rule-based indicators for the operator to check (camera view, field report) — not confirmed incidents. Emergency pre-emption can be
            triggered from Signal Simulation (simulated only).
          </p>
        </Panel>

        <Panel title="Incident Log" bodyClassName="overflow-auto max-h-[520px]">
          <table className="w-full text-[12px]">
            <thead className="sticky top-0 bg-ink-900 text-[11px] uppercase tracking-wider text-txt-dim">
              <tr>
                {['Started', 'Duration', 'Type', 'Approach', 'Details', ''].map((h) => <th key={h} className="px-3 py-2 text-left font-normal">{h}</th>)}
              </tr>
            </thead>
            <tbody>
              {history.map((r) => (
                <tr key={r.id} className="border-t border-line-soft/60 align-top">
                  <td className="num whitespace-nowrap px-3 py-1.5 text-txt-dim">{new Date(r.started * 1000).toLocaleString([], { dateStyle: 'short', timeStyle: 'medium' })}</td>
                  <td className="num whitespace-nowrap px-3">{r.ended ? secs(r.ended - r.started) : <span className="text-crit">active</span>}</td>
                  <td className={`whitespace-nowrap px-3 ${r.severity === 'critical' ? 'text-crit' : 'text-warn'}`}>{INCIDENT_LABEL[r.kind]}</td>
                  <td className="px-3">{r.approach ? APPROACH_LABEL[r.approach] : '—'}</td>
                  <td className="px-3 text-[11px]">{r.message}{(r.source === 'demo' || r.source === 'mixed') && <span className="ml-1 text-[9px] font-semibold text-warn">{r.source === 'demo' ? 'SIM' : 'MIXED'}</span>}</td>
                  <td className="px-3 text-[10px] text-txt-mute">{r.acknowledged ? 'ack' : ''}</td>
                </tr>
              ))}
              {history.length === 0 && <tr><td colSpan={6} className="p-3 text-txt-dim">No incidents recorded at this site.</td></tr>}
            </tbody>
          </table>
        </Panel>
      </div>

      <Panel title="Detection Rules" bodyClassName="p-3 space-y-3">
        <div className="space-y-1.5 text-[11px] leading-relaxed text-txt-dim">
          <p><span className="text-crit">Blocked discharge</span> — green running, vehicles queued, but none crossing the stop line: possible breakdown, crash or obstruction.</p>
          <p><span className="text-warn">Stalled vehicle</span> — a vehicle stationary in the queue far longer than any normal cycle.</p>
          <p><span className="text-warn">Queue spillback</span> — queue reaching the end of the monitored section.</p>
          <p><span className="text-warn">Camera failure</span> — a configured camera offline.</p>
        </div>
        {cfg ? (
          <>
            <div className="grid grid-cols-2 gap-3">
              {CFG_FIELDS.map((f) => (
                <Field key={f.k} label={f.label}>
                  <input type="number" className="input num" value={cfg[f.k]} onChange={(e) => setCfg({ ...cfg, [f.k]: Number(e.target.value) })} />
                </Field>
              ))}
            </div>
            <button className="btn btn-primary" onClick={saveCfg}>
              <Save size={12} /> Apply thresholds
            </button>
            {msg && <div className={`text-[12px] ${msg.ok ? 'text-ok' : 'text-crit'}`}>{msg.text}</div>}
          </>
        ) : (
          <Waiting />
        )}
      </Panel>
    </PageGrid>
  )
}
