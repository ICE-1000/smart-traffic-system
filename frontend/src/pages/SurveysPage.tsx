import { Download, Plus, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Panel, Waiting } from '../components/Panel'
import { Field, PageGrid } from '../components/ui'
import { useLiveData } from '../hooks/useLiveData'
import { api } from '../services/api'

interface McResult {
  flow_vph?: number
  mean_journey_time_min?: number
  space_mean_speed_kmh?: number
  ci?: number | null
  tti?: number | null
  error?: string
}
interface McRun {
  id: number
  corridor: string
  direction: string
  run_time: number
  period: string
  distance_km: number
  tw_min: number
  ta_min: number
  x: number
  y: number
  free_flow_kmh: number | null
  notes: string | null
  result: McResult
}
interface McSummary {
  corridor: string
  direction: string
  period: string
  runs: number
  mean_flow_vph: number
  mean_journey_time_min: number
  mean_speed_kmh: number
  mean_ci: number | null
}
interface Session {
  id: number
  camera_id: string
  start_ts: number
  end_ts: number
  duration_min: number
  manual_count: number
  system_count: number
  manual_mean_wait_s: number | null
  system_mean_wait_s: number | null
  error_pct: number | null
  accuracy_pct: number | null
  wait_error_pct?: number
  notes: string | null
}

const PERIOD: Record<string, string> = { am_peak: 'AM peak', pm_peak: 'PM peak', off_peak: 'Off-peak', night: 'Night' }
const toLocalInput = (d: Date) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
const fromLocalInput = (s: string) => new Date(s).getTime() / 1000
const fmtTime = (ts: number) => new Date(ts * 1000).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' })

export function SurveysPage() {
  const { snapshot } = useLiveData()
  const [runs, setRuns] = useState<McRun[]>([])
  const [summary, setSummary] = useState<McSummary[]>([])
  const [sessions, setSessions] = useState<Session[]>([])
  const [overall, setOverall] = useState<{ sessions: number; manual_total: number; system_total: number; accuracy_pct: number | null; error_pct: number | null } | null>(null)
  const [mc, setMc] = useState({ corridor: '', direction: 'Northbound', when: toLocalInput(new Date()), distance_km: '', tw_min: '', ta_min: '', x: '', y: '', free_flow_kmh: '', notes: '' })
  const [vc, setVc] = useState({ camera_id: 'CAM-01', start: toLocalInput(new Date(Date.now() - 15 * 60000)), end: toLocalInput(new Date()), manual_count: '', manual_mean_wait_s: '', notes: '' })
  const [msg, setMsg] = useState<{ ok: boolean; text: string; where: 'mc' | 'vc' } | null>(null)

  const load = useCallback(() => {
    api.get<{ runs: McRun[]; summary: McSummary[] }>('/api/surveys/moving-car').then((r) => { setRuns(r.runs); setSummary(r.summary) }).catch(() => undefined)
    api.get<{ sessions: Session[]; overall: typeof overall }>('/api/surveys/validation').then((r) => { setSessions(r.sessions); setOverall(r.overall) }).catch(() => undefined)
  }, [])
  useEffect(() => {
    load()
  }, [load, snapshot?.site.id])

  if (!snapshot) return <Waiting />
  const num = (v: string) => (v.trim() === '' ? null : Number(v))

  const addRun = () =>
    api
      .post('/api/surveys/moving-car', {
        corridor: mc.corridor || snapshot.site.corridor || snapshot.site.name,
        direction: mc.direction,
        run_time: fromLocalInput(mc.when),
        distance_km: num(mc.distance_km),
        tw_min: num(mc.tw_min),
        ta_min: num(mc.ta_min),
        x: num(mc.x),
        y: num(mc.y),
        free_flow_kmh: num(mc.free_flow_kmh),
        notes: mc.notes || null,
      })
      .then(() => { setMsg({ ok: true, text: 'Run pair saved.', where: 'mc' }); load() })
      .catch((e: Error) => setMsg({ ok: false, text: e.message, where: 'mc' }))
  const addSession = () =>
    api
      .post('/api/surveys/validation', {
        camera_id: vc.camera_id,
        start_ts: fromLocalInput(vc.start),
        end_ts: fromLocalInput(vc.end),
        manual_count: num(vc.manual_count),
        manual_mean_wait_s: num(vc.manual_mean_wait_s),
        notes: vc.notes || null,
      })
      .then(() => { setMsg({ ok: true, text: 'Session saved and compared.', where: 'vc' }); load() })
      .catch((e: Error) => setMsg({ ok: false, text: e.message, where: 'vc' }))
  const delRun = (id: number) => confirm('Delete this run pair?') && api.del(`/api/surveys/moving-car/${id}`).then(load)
  const delSession = (id: number) => confirm('Delete this session?') && api.del(`/api/surveys/validation/${id}`).then(load)
  const inp = (obj: Record<string, string>, set: (v: never) => void, k: string, props: Record<string, unknown> = {}) => (
    <input className="input num" value={obj[k]} onChange={(e) => set({ ...obj, [k]: e.target.value } as never)} {...props} />
  )

  return (
    <PageGrid className="space-y-3">
      <div className="border border-line-soft bg-ink-900/80 px-3 py-2 text-[11px] leading-relaxed text-txt-dim">
        Field data for <span className="text-white">{snapshot.site.name}</span>
        {snapshot.site.corridor && <> ({snapshot.site.corridor})</>}. The proposal's data-ingestion methods: <span className="text-white">Moving Car Method</span> audits for
        corridor travel time and Congestion Index, and <span className="text-white">manual counts</span> to validate the camera + AI measurements. Schedule
        sessions in the proposal's peak periods (07:00–09:00, 16:00–19:00) and at least one off-peak period for the free-flow reference.
      </div>

      <div className="grid items-start gap-3 2xl:grid-cols-2">
        <Panel
          title="Moving Car Method (Wardrop & Charlesworth, 1954)"
          actions={<a className="btn py-0.5" href="/api/surveys/moving-car.csv" download><Download size={11} /> CSV</a>}
          bodyClassName="p-3 space-y-3"
        >
          <p className="text-[11px] leading-relaxed text-txt-dim">
            Drive the section once <b className="text-txt">with</b> the stream (time t<sub>w</sub>, count y = vehicles overtaking you − vehicles you overtake) and once
            <b className="text-txt"> against</b> it (time t<sub>a</sub>, count x = stream vehicles met). Flow q = (x+y)/(t<sub>a</sub>+t<sub>w</sub>); mean journey time
            t̄ = t<sub>w</sub> − y/q; CI = (t̄ − t<sub>free</sub>)/t<sub>free</sub>.
          </p>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Field label="Corridor / section"><input className="input" placeholder={snapshot.site.corridor ?? ''} value={mc.corridor} onChange={(e) => setMc({ ...mc, corridor: e.target.value })} /></Field>
            <Field label="Stream direction"><input className="input" value={mc.direction} onChange={(e) => setMc({ ...mc, direction: e.target.value })} /></Field>
            <Field label="Date & time of runs"><input type="datetime-local" className="input" value={mc.when} onChange={(e) => setMc({ ...mc, when: e.target.value })} /></Field>
            <Field label="Section length (km)">{inp(mc, setMc as never, 'distance_km', { type: 'number', step: 0.01 })}</Field>
            <Field label="tw — with stream (min)">{inp(mc, setMc as never, 'tw_min', { type: 'number', step: 0.01 })}</Field>
            <Field label="ta — against stream (min)">{inp(mc, setMc as never, 'ta_min', { type: 'number', step: 0.01 })}</Field>
            <Field label="x — vehicles met">{inp(mc, setMc as never, 'x', { type: 'number' })}</Field>
            <Field label="y — overtaking − overtaken">{inp(mc, setMc as never, 'y', { type: 'number' })}</Field>
            <Field label="Free-flow speed (km/h)">{inp(mc, setMc as never, 'free_flow_kmh', { type: 'number', placeholder: 'from off-peak runs' })}</Field>
            <div className="md:col-span-3"><Field label="Notes"><input className="input" value={mc.notes} onChange={(e) => setMc({ ...mc, notes: e.target.value })} /></Field></div>
          </div>
          <button className="btn btn-primary" onClick={addRun}><Plus size={12} /> Save run pair</button>
          {msg?.where === 'mc' && <div className={`text-[12px] ${msg.ok ? 'text-ok' : 'text-crit'}`}>{msg.text}</div>}

          {summary.length > 0 && (
            <table className="w-full text-[11px]">
              <thead className="text-txt-dim">
                <tr>{['Corridor', 'Direction', 'Period', 'Runs', 'Flow', 'Journey time', 'Speed', 'Mean CI'].map((h) => <th key={h} className="py-1 text-left font-normal">{h}</th>)}</tr>
              </thead>
              <tbody>
                {summary.map((r) => (
                  <tr key={`${r.corridor}${r.direction}${r.period}`} className="border-t border-line-soft/60">
                    <td className="py-1 text-white">{r.corridor}</td>
                    <td>{r.direction}</td>
                    <td>{PERIOD[r.period]}</td>
                    <td className="num">{r.runs}</td>
                    <td className="num">{r.mean_flow_vph} veh/h</td>
                    <td className="num">{r.mean_journey_time_min} min</td>
                    <td className="num">{r.mean_speed_kmh} km/h</td>
                    <td className="num text-num">{r.mean_ci ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <div className="max-h-[300px] overflow-auto">
            <table className="w-full text-[11px]">
              <thead className="sticky top-0 bg-ink-900 text-txt-dim">
                <tr>{['When', 'Period', 'Corridor', 'Dir', 'km', 'tw', 'ta', 'x', 'y', 'q veh/h', 't̄ min', 'km/h', 'CI', ''].map((h) => <th key={h} className="py-1 pr-2 text-left font-normal">{h}</th>)}</tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.id} className="num border-t border-line-soft/60">
                    <td className="py-1 pr-2">{fmtTime(r.run_time)}</td>
                    <td className="pr-2">{PERIOD[r.period]}</td>
                    <td className="pr-2">{r.corridor}</td>
                    <td className="pr-2">{r.direction}</td>
                    <td className="pr-2">{r.distance_km}</td>
                    <td className="pr-2">{r.tw_min}</td>
                    <td className="pr-2">{r.ta_min}</td>
                    <td className="pr-2">{r.x}</td>
                    <td className="pr-2">{r.y}</td>
                    {r.result.error ? <td colSpan={4} className="text-crit">{r.result.error}</td> : (
                      <>
                        <td className="pr-2">{r.result.flow_vph}</td>
                        <td className="pr-2">{r.result.mean_journey_time_min}</td>
                        <td className="pr-2">{r.result.space_mean_speed_kmh}</td>
                        <td className="pr-2 text-num">{r.result.ci ?? '—'}</td>
                      </>
                    )}
                    <td><button className="text-txt-mute hover:text-crit" onClick={() => delRun(r.id)} title="Delete"><Trash2 size={12} /></button></td>
                  </tr>
                ))}
                {runs.length === 0 && <tr><td colSpan={14} className="py-2 text-txt-dim">No runs recorded at this site yet.</td></tr>}
              </tbody>
            </table>
          </div>
        </Panel>

        <Panel title="Validation — Manual Count vs Camera + AI" bodyClassName="p-3 space-y-3">
          <p className="text-[11px] leading-relaxed text-txt-dim">
            Count vehicles entering the camera's approach area with a tally counter for 10–15 minutes (optionally stopwatch the waiting time of several
            vehicles), then enter the session here. The system compares it with the vehicles it tracked in the same window.
          </p>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
            <Field label="Camera">
              <select className="input" value={vc.camera_id} onChange={(e) => setVc({ ...vc, camera_id: e.target.value })}>
                {snapshot.cameras.map((c) => <option key={c.id} value={c.id}>{c.id} · {c.approach}</option>)}
              </select>
            </Field>
            <Field label="Start"><input type="datetime-local" className="input" value={vc.start} onChange={(e) => setVc({ ...vc, start: e.target.value })} /></Field>
            <Field label="End"><input type="datetime-local" className="input" value={vc.end} onChange={(e) => setVc({ ...vc, end: e.target.value })} /></Field>
            <Field label="Manual count (vehicles)">{inp(vc, setVc as never, 'manual_count', { type: 'number', min: 0 })}</Field>
            <Field label="Manual mean wait (s, optional)">{inp(vc, setVc as never, 'manual_mean_wait_s', { type: 'number', min: 0 })}</Field>
            <Field label="Notes"><input className="input" value={vc.notes} onChange={(e) => setVc({ ...vc, notes: e.target.value })} /></Field>
          </div>
          <button className="btn btn-primary" onClick={addSession}><Plus size={12} /> Save & compare</button>
          {msg?.where === 'vc' && <div className={`text-[12px] ${msg.ok ? 'text-ok' : 'text-crit'}`}>{msg.text}</div>}
          {overall && overall.sessions > 0 && (
            <div className="grid grid-cols-3 gap-3 border-y border-line-soft py-2">
              <div><div className="text-[11px] text-txt-dim">Sessions</div><div className="num text-[20px] text-num">{overall.sessions}</div></div>
              <div><div className="text-[11px] text-txt-dim">Manual / system total</div><div className="num text-[20px] text-num">{overall.manual_total} / {overall.system_total}</div></div>
              <div><div className="text-[11px] text-txt-dim">Overall count accuracy</div><div className="num text-[20px] text-num">{overall.accuracy_pct ?? '—'}%</div></div>
            </div>
          )}
          <div className="max-h-[300px] overflow-auto">
            <table className="w-full text-[11px]">
              <thead className="sticky top-0 bg-ink-900 text-txt-dim">
                <tr>{['Camera', 'Start', 'Min', 'Manual', 'System', 'Error', 'Accuracy', 'Wait M/S', ''].map((h) => <th key={h} className="py-1 pr-2 text-left font-normal">{h}</th>)}</tr>
              </thead>
              <tbody>
                {sessions.map((r) => (
                  <tr key={r.id} className="num border-t border-line-soft/60">
                    <td className="py-1 pr-2 text-white">{r.camera_id}</td>
                    <td className="pr-2">{fmtTime(r.start_ts)}</td>
                    <td className="pr-2">{r.duration_min}</td>
                    <td className="pr-2">{r.manual_count}</td>
                    <td className="pr-2">{r.system_count}</td>
                    <td className="pr-2">{r.error_pct !== null ? `${r.error_pct > 0 ? '+' : ''}${r.error_pct}%` : '—'}</td>
                    <td className="pr-2 text-num">{r.accuracy_pct !== null ? `${r.accuracy_pct}%` : '—'}</td>
                    <td className="pr-2">{r.manual_mean_wait_s ?? '—'} / {r.system_mean_wait_s ?? '—'} s</td>
                    <td><button className="text-txt-mute hover:text-crit" onClick={() => delSession(r.id)} title="Delete"><Trash2 size={12} /></button></td>
                  </tr>
                ))}
                {sessions.length === 0 && <tr><td colSpan={9} className="py-2 text-txt-dim">No validation sessions yet.</td></tr>}
              </tbody>
            </table>
          </div>
          <p className="text-[10px] leading-relaxed text-txt-mute">
            System count = vehicle tracks that entered the approach area during the window (one per vehicle, from ByteTrack IDs). Accuracy = 100 − |error %|.
          </p>
        </Panel>
      </div>
    </PageGrid>
  )
}
