import { Plus, Save } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Panel, Waiting } from '../components/Panel'
import { Field, PageGrid, StatusRow, type Health } from '../components/ui'
import { useLiveData } from '../hooks/useLiveData'
import { APPROACH_LABEL, secs } from '../lib/format'
import { api } from '../services/api'
import type { DataSourceMode, NodeType, Site } from '../types/traffic'

interface SelfTest {
  status: 'not_run' | 'running' | 'passed' | 'failed'
  ok?: boolean
  ts?: number
  model?: string
  model_path?: string
  torch?: string
  python?: string
  load_ms?: number
  infer_ms?: number
  detections?: number
  classes?: Record<string, number>
  tracker?: string
  tracker_note?: string
  error?: string
  hint?: string
}

function AiSelfTest() {
  const [st, setSt] = useState<SelfTest | null>(null)
  const [imgT, setImgT] = useState(0)
  useEffect(() => {
    let timer: number | undefined
    const poll = () =>
      api.get<SelfTest>('/api/vision/selftest').then((r) => {
        setSt(r)
        if (r.status === 'running') timer = window.setTimeout(poll, 1500)
        else setImgT(r.ts ?? Date.now())
      }).catch(() => undefined)
    poll()
    return () => window.clearTimeout(timer)
  }, [])
  const run = () => {
    setSt({ status: 'running' })
    api.post<SelfTest>('/api/vision/selftest', {}).then(() => {
      const poll = () => api.get<SelfTest>('/api/vision/selftest').then((r) => {
        setSt(r)
        if (r.status === 'running') window.setTimeout(poll, 1500)
        else setImgT(r.ts ?? Date.now())
      })
      window.setTimeout(poll, 1500)
    })
  }
  const colour = st?.status === 'passed' ? 'text-ok' : st?.status === 'failed' ? 'text-crit' : 'text-warn'
  return (
    <div className="space-y-2 border-t border-line-soft pt-3">
      <div className="flex items-center gap-2">
        <span className="text-[12px] text-white">Model self-test</span>
        <span className={`text-[11px] font-semibold uppercase tracking-wider ${colour}`}>
          {st ? (st.status === 'not_run' ? 'not run' : st.status) : '…'}
        </span>
        <button className="btn ml-auto py-0.5" onClick={run} disabled={st?.status === 'running'}>
          {st?.status === 'running' ? 'Testing…' : 'Test AI model'}
        </button>
      </div>
      {st?.status === 'passed' && (
        <div className="grid grid-cols-[1fr_140px] gap-3">
          <div className="num space-y-0.5 text-[11px] text-txt-dim">
            <div>Detected <b className="text-white">{st.detections}</b> objects on the test image: {Object.entries(st.classes ?? {}).map(([k, n]) => `${k} ${n}`).join(', ')}</div>
            <div>Inference <b className="text-white">{st.infer_ms} ms</b> · model load {st.load_ms} ms</div>
            <div>Tracker <b className="text-white">{st.tracker === 'bytetrack' ? 'ByteTrack' : 'IoU fallback'}</b>{st.tracker_note ? ` — ${st.tracker_note}` : ''}</div>
            <div>Python {st.python} · PyTorch {st.torch}</div>
          </div>
          {imgT > 0 && <img src={`/api/vision/selftest.jpg?t=${imgT}`} alt="Self-test detections" className="w-full border border-line" />}
        </div>
      )}
      {st?.status === 'failed' && (
        <div className="space-y-1 border border-crit/60 bg-crit/10 p-2 text-[11px]">
          <div className="text-crit">{st.error}</div>
          <div className="text-white">Fix: {st.hint}</div>
        </div>
      )}
    </div>
  )
}

interface VisionCfg {
  enabled: boolean
  model: string
  conf: number
  imgsz: number
  device: string | null
}
const MODES: { id: DataSourceMode; label: string; text: string }[] = [
  { id: 'auto', label: 'Auto', text: 'Camera + AI where a camera is working; demo model (labelled SIMULATED) elsewhere.' },
  { id: 'vision', label: 'Cameras only', text: 'Only real measurements. Approaches without a working camera show NO DATA and get fixed-time fallback service.' },
  { id: 'demo', label: 'Demo only', text: 'Cameras and AI stopped; everything comes from the demo model. Useful for presentations without phones.' },
]

const NODE_LABEL: Record<NodeType, string> = { signalised: 'Signalised junction', roundabout: 'Roundabout', unconfirmed: 'Unconfirmed' }

function SitesPanel({ activeId }: { activeId: string }) {
  const [sites, setSites] = useState<Site[]>([])
  const [edit, setEdit] = useState<Site | null>(null)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const load = () => api.get<Site[]>('/api/sites').then(setSites).catch(() => undefined)
  useEffect(() => {
    load()
  }, [activeId])
  const save = () =>
    edit &&
    api
      .post('/api/sites', edit)
      .then(() => { setMsg({ ok: true, text: `Saved ${edit.name}.` }); setEdit(null); load() })
      .catch((e: Error) => setMsg({ ok: false, text: e.message }))
  const activate = (s: Site) =>
    confirm(`Make ${s.name} the active study site? New measurements will be recorded under it.`) &&
    api.post('/api/sites/active', { id: s.id }).then(load)
  return (
    <Panel
      title="Study Sites (proposal study nodes)"
      className="lg:col-span-2"
      actions={<button className="btn py-0.5" onClick={() => setEdit({ id: '', name: '', node_type: 'signalised', corridor: '', description: '' })}><Plus size={11} /> Add site</button>}
      bodyClassName="p-3 space-y-3"
    >
      <table className="w-full text-[12px]">
        <thead className="text-[11px] uppercase tracking-wider text-txt-dim">
          <tr>{['ID', 'Name', 'Corridor', 'Control type', 'Description', ''].map((h) => <th key={h} className="py-1.5 pr-3 text-left font-normal">{h}</th>)}</tr>
        </thead>
        <tbody>
          {sites.map((x) => (
            <tr key={x.id} className={`border-t border-line-soft/60 ${x.id === activeId ? 'bg-[#1d5fc4]/20' : ''}`}>
              <td className="num whitespace-nowrap py-1.5 pr-3 text-white">{x.id}</td>
              <td className="pr-3">{x.name}{x.id === activeId && <span className="ml-2 text-[10px] font-semibold text-ok">ACTIVE</span>}</td>
              <td className="whitespace-nowrap pr-3 text-txt-dim">{x.corridor ?? '—'}</td>
              <td className={`pr-3 ${x.node_type === 'unconfirmed' ? 'text-warn' : ''}`}>{NODE_LABEL[x.node_type]}</td>
              <td className="pr-3 text-[11px] text-txt-dim">{x.description}</td>
              <td className="whitespace-nowrap">
                <button className="btn mr-1 py-0" onClick={() => setEdit({ ...x })}>Edit</button>
                {x.id !== activeId && <button className="btn py-0" onClick={() => activate(x)}>Activate</button>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {edit && (
        <div className="grid grid-cols-2 gap-3 border-t border-line-soft pt-3 md:grid-cols-5">
          <Field label="Site ID"><input className="input" value={edit.id} disabled={sites.some((x) => x.id === edit.id) && edit.id !== ''} onChange={(e) => setEdit({ ...edit, id: e.target.value })} /></Field>
          <Field label="Name"><input className="input" value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} /></Field>
          <Field label="Corridor"><input className="input" value={edit.corridor ?? ''} onChange={(e) => setEdit({ ...edit, corridor: e.target.value })} /></Field>
          <Field label="Control type">
            <select className="input" value={edit.node_type} onChange={(e) => setEdit({ ...edit, node_type: e.target.value as NodeType })}>
              {(Object.keys(NODE_LABEL) as NodeType[]).map((k) => <option key={k} value={k}>{NODE_LABEL[k]}</option>)}
            </select>
          </Field>
          <Field label="Description"><input className="input" value={edit.description ?? ''} onChange={(e) => setEdit({ ...edit, description: e.target.value })} /></Field>
          <div className="flex gap-2 md:col-span-5">
            <button className="btn btn-primary" onClick={save}><Save size={12} /> Save site</button>
            <button className="btn" onClick={() => setEdit(null)}>Cancel</button>
          </div>
        </div>
      )}
      {msg && <div className={`text-[12px] ${msg.ok ? 'text-ok' : 'text-crit'}`}>{msg.text}</div>}
      <p className="text-[10px] leading-relaxed text-txt-mute">
        Kafue Roundabout, Hybrid Roundabout and City Market Cross are the proposal's study nodes. Confirm each site's control type on site. At a roundabout
        the cameras, queues, CI, incidents and surveys apply directly; the signal plan, priority decisions and adaptive-vs-fixed evaluation describe a
        hypothetical signalised operation. One site is active at a time — move the phones with you.
      </p>
    </Panel>
  )
}

export function SettingsPage() {
  const { snapshot, wsStatus } = useLiveData()
  const [vision, setVision] = useState<VisionCfg | null>(null)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.get<VisionCfg>('/api/vision/config').then(setVision).catch(() => undefined)
  }, [])

  if (!snapshot) return <Waiting />
  const s = snapshot.system
  const camOnline = snapshot.cameras.filter((c) => c.status === 'online').length
  const configured = snapshot.cameras.filter((c) => c.has_stream_url && c.enabled).length
  const camState: Health = configured === 0 ? 'idle' : camOnline === configured ? 'ok' : camOnline > 0 ? 'warn' : 'error'
  const aiState: Health = s.ai_model === 'running' ? 'ok' : s.ai_model === 'error' ? 'error' : s.ai_model === 'loading' ? 'warn' : 'idle'
  const onlineCams = snapshot.cameras.filter((c) => c.status === 'online')
  const avgCamFps = onlineCams.length ? onlineCams.reduce((a, c) => a + c.camera_fps, 0) / onlineCams.length : null

  const setMode = (m: DataSourceMode) =>
    api.post('/api/system/config', { data_source: m }).then(() => setMsg({ ok: true, text: `Data source: ${m}` })).catch((e: Error) => setMsg({ ok: false, text: e.message }))
  const saveVision = () => {
    if (!vision) return
    setBusy(true)
    api
      .post<VisionCfg>('/api/vision/config', vision)
      .then((v) => {
        setVision(v)
        setMsg({ ok: true, text: 'AI settings applied (a model change reloads the workers).' })
      })
      .catch((e: Error) => setMsg({ ok: false, text: e.message }))
      .finally(() => setBusy(false))
  }

  return (
    <PageGrid className="grid items-start gap-3 lg:grid-cols-2 2xl:grid-cols-3">
      <Panel title="System Status" bodyClassName="px-3">
        <StatusRow label="Backend (FastAPI)" state={s.backend === 'ok' ? 'ok' : 'error'} value={`up ${secs(s.uptime_s)}`} />
        <StatusRow label="WebSocket" state={wsStatus === 'open' ? 'ok' : wsStatus === 'connecting' ? 'warn' : 'error'} value={`${wsStatus} · ${s.websocket_clients} client(s)`} />
        <StatusRow label="Database" state={s.database === 'ok' ? 'ok' : 'error'} value={s.database} />
        <StatusRow label="Camera connections" state={camState} value={`${camOnline}/${configured} configured online`} />
        <StatusRow label={`AI model (${s.ai_model_name})`} state={aiState} value={s.ai_model} hint={s.ai_model_error ?? undefined} />
        <StatusRow label="Video processing" state={s.video_processing.startsWith('running') ? 'ok' : 'idle'} value={s.video_processing} />
        <StatusRow
          label="Measurement source"
          state={snapshot.source === 'vision' ? 'ok' : 'warn'}
          value={snapshot.source === 'vision' ? 'camera + AI' : snapshot.source === 'demo' ? 'DEMO (simulated)' : snapshot.source === 'none' ? 'no data' : 'mixed'}
        />
        {s.ai_model_error && <p className="pb-1 text-[11px] text-crit">Model error: {s.ai_model_error}</p>}
        {s.ai_hint && s.ai_model_error && <p className="pb-2 text-[11px] text-white">Fix: {s.ai_hint}</p>}
      </Panel>

      <Panel title="Performance" bodyClassName="px-3">
        <StatusRow label="Processing FPS (all feeds)" state={s.processing_fps ? 'ok' : 'idle'} value={s.processing_fps ?? '—'} />
        <StatusRow label="Camera FPS (average)" state={avgCamFps ? 'ok' : 'idle'} value={avgCamFps !== null ? avgCamFps.toFixed(1) : '—'} />
        <StatusRow label="Detection time" state={s.detection_ms === null ? 'idle' : s.detection_ms > 250 ? 'warn' : 'ok'} value={s.detection_ms !== null ? `${s.detection_ms} ms/frame` : '—'} />
        <StatusRow label="Active feeds" state={s.active_feeds ? 'ok' : 'idle'} value={s.active_feeds} />
        <StatusRow label="Backend CPU (process)" state={s.cpu_percent > 85 * navigator.hardwareConcurrency ? 'warn' : 'ok'} value={`${s.cpu_percent}%`} hint="Per-core percentage: 200% = two cores busy" />
        <StatusRow label="System CPU" state={s.system_cpu_percent > 85 ? 'warn' : 'ok'} value={`${s.system_cpu_percent}%`} />
        <StatusRow label="Backend memory" state="ok" value={`${s.memory_mb} MB (system ${s.system_memory_percent}%)`} />
        <StatusRow label="Analysis tick time" state={s.tick_ms > 200 ? 'warn' : 'ok'} value={`${s.tick_ms} ms`} />
      </Panel>

      <Panel title="Per-camera Processing" bodyClassName="overflow-auto">
        <table className="w-full text-[11px]">
          <thead className="text-txt-dim">
            <tr>
              {['Camera', 'Status', 'Cam fps', 'AI fps', 'ms/frame', 'Tracks'].map((h) => <th key={h} className="px-3 py-2 text-left font-normal">{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {snapshot.cameras.map((c) => (
              <tr key={c.id} className="border-t border-line-soft/60">
                <td className="px-3 py-1.5 text-white">{c.id} <span className="text-txt-dim">{APPROACH_LABEL[c.approach]}</span></td>
                <td className="px-3">{c.status.replace('_', ' ')}{c.is_sample ? ' (sample)' : ''}</td>
                <td className="num px-3">{c.status === 'online' ? c.camera_fps.toFixed(1) : '—'}</td>
                <td className="num px-3">{c.vision?.status === 'detecting' ? c.vision.processing_fps.toFixed(1) : '—'}</td>
                <td className="num px-3">{c.vision?.status === 'detecting' ? c.vision.detection_ms.toFixed(0) : '—'}</td>
                <td className="num px-3">{c.vision?.active_tracks ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="px-3 py-2 text-[10px] leading-relaxed text-txt-mute">
          Benchmark on your laptop with <span className="font-mono">python scripts/benchmark.py</span>. If ms/frame × feeds × fps approaches 1000 ms, lower the
          processing fps or width per camera (Camera Management) or the AI image size below.
        </p>
      </Panel>

      <Panel title="Data Source" bodyClassName="p-3 space-y-2">
        {MODES.map((m) => (
          <label key={m.id} className={`flex cursor-pointer gap-3 border p-2 ${snapshot.data_source_mode === m.id ? 'border-sky-accent bg-[#1565c0]/20' : 'border-line-soft'}`}>
            <input type="radio" name="ds" checked={snapshot.data_source_mode === m.id} onChange={() => setMode(m.id)} />
            <span>
              <span className="block text-[12px] text-white">{m.label}</span>
              <span className="text-[11px] text-txt-dim">{m.text}</span>
            </span>
          </label>
        ))}
      </Panel>

      <Panel title="AI Detection (YOLO + ByteTrack)" bodyClassName="p-3 space-y-3">
        {vision ? (
          <>
            <label className="flex items-center gap-2 text-[12px]">
              <input type="checkbox" checked={vision.enabled} onChange={(e) => setVision({ ...vision, enabled: e.target.checked })} /> Detection enabled
            </label>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Model weights">
                <input className="input font-mono" value={vision.model} onChange={(e) => setVision({ ...vision, model: e.target.value })} />
              </Field>
              <Field label="Device (blank = auto)">
                <input className="input font-mono" placeholder="cpu / intel:gpu / 0" value={vision.device ?? ''} onChange={(e) => setVision({ ...vision, device: e.target.value || null })} />
              </Field>
              <Field label={`Min confidence · ${vision.conf.toFixed(2)}`}>
                <input type="range" min={0.1} max={0.8} step={0.05} value={vision.conf} onChange={(e) => setVision({ ...vision, conf: Number(e.target.value) })} className="w-full accent-sky-400" />
              </Field>
              <Field label="Inference size (px)">
                <select className="input" value={vision.imgsz} onChange={(e) => setVision({ ...vision, imgsz: Number(e.target.value) })}>
                  {[320, 416, 480, 640, 800].map((v) => <option key={v} value={v}>{v}</option>)}
                </select>
              </Field>
            </div>
            <button className="btn btn-primary" disabled={busy} onClick={saveVision}>
              <Save size={12} /> Apply
            </button>
            <AiSelfTest />
            <p className="text-[10px] leading-relaxed text-txt-mute">
              Default: yolo26n.pt (Ultralytics nano, COCO-pretrained; included in the models folder). Classes used: car, motorcycle, bus, truck; person and bicycle are shown separately.
              Ultralytics is AGPL-3.0 — fine for research; commercial deployment needs a licence.
            </p>
          </>
        ) : (
          <Waiting />
        )}
        {msg && <div className={`text-[12px] ${msg.ok ? 'text-ok' : 'text-crit'}`}>{msg.text}</div>}
      </Panel>

      <SitesPanel activeId={snapshot.site.id} />

      <Panel title="About This Prototype" bodyClassName="p-3 space-y-2 text-[12px] leading-relaxed text-txt-dim">
        <p><span className="text-white">Phones are the eyes, the laptop is the brain, the dashboard is the control centre.</span></p>
        <p>Phone streams → OpenCV receivers → YOLO + ByteTrack → queue / wait measurement → congestion score → priority decision → simulated signals → this dashboard.</p>
        <p className="border-l-2 border-warn pl-2 text-warn">Safety: research and simulation only. Not connected to, and must not be connected to, operational traffic signals. Real deployment requires the road authority, qualified traffic engineers, approved equipment and formal safety validation.</p>
        <p>API documentation: <a className="text-sky-accent underline" href="/docs" target="_blank" rel="noreferrer">/docs</a></p>
      </Panel>
    </PageGrid>
  )
}
