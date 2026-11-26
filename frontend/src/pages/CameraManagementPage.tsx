import { Plus, RefreshCw, Save, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Panel, Waiting } from '../components/Panel'
import { RegionEditor } from '../components/RegionEditor'
import { Field, PageGrid, StatusDot, type Health } from '../components/ui'
import { useLiveData } from '../hooks/useLiveData'
import { APPROACH_LABEL, clockSec } from '../lib/format'
import { api } from '../services/api'
import type { Approach, CameraInfo } from '../types/traffic'
import { APPROACHES } from '../types/traffic'

type Draft = Pick<CameraInfo, 'id' | 'name' | 'approach' | 'stream_url' | 'enabled' | 'processing_width' | 'processing_fps'>
const EMPTY: Draft = { id: '', name: '', approach: 'north', stream_url: '', enabled: true, processing_width: 640, processing_fps: 5 }
const HEALTH: Record<CameraInfo['status'], Health> = { online: 'ok', connecting: 'warn', offline: 'error', not_configured: 'idle', disabled: 'idle' }

export function CameraManagementPage() {
  const { snapshot } = useLiveData()
  const [sel, setSel] = useState<string | null>(null)
  const [draft, setDraft] = useState<Draft>(EMPTY)
  const [isNew, setIsNew] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [busy, setBusy] = useState(false)

  const cams = snapshot?.cameras ?? []
  useEffect(() => {
    if (!sel && cams.length && !isNew) pick(cams[0])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cams.length])

  function pick(c: CameraInfo) {
    setSel(c.id)
    setIsNew(false)
    setMsg(null)
    setDraft({ id: c.id, name: c.name, approach: c.approach, stream_url: c.stream_url, enabled: c.enabled, processing_width: c.processing_width, processing_fps: c.processing_fps })
  }

  async function save() {
    setBusy(true)
    setMsg(null)
    try {
      await api.post('/api/cameras', draft)
      setMsg({ ok: true, text: `Saved ${draft.id}.` })
      setSel(draft.id)
      setIsNew(false)
    } catch (e) {
      setMsg({ ok: false, text: (e as Error).message })
    } finally {
      setBusy(false)
    }
  }

  async function reconnect() {
    if (!sel) return
    try {
      await api.post(`/api/cameras/${encodeURIComponent(sel)}/reconnect`, {})
      setMsg({ ok: true, text: `Reconnecting ${sel}…` })
    } catch (e) {
      setMsg({ ok: false, text: (e as Error).message })
    }
  }

  async function remove() {
    if (!sel || !confirm(`Delete camera ${sel}?`)) return
    try {
      await api.del(`/api/cameras/${encodeURIComponent(sel)}`)
      setSel(null)
      setDraft(EMPTY)
      setMsg({ ok: true, text: `Deleted ${sel}.` })
    } catch (e) {
      setMsg({ ok: false, text: (e as Error).message })
    }
  }

  if (!snapshot) return <Waiting />
  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setDraft((d) => ({ ...d, [k]: v }))

  return (
    <PageGrid className="grid grid-cols-1 items-start gap-3 2xl:grid-cols-[1.4fr_1fr]">
      <Panel
        title="Camera Feeds"
        actions={
          <button className="btn py-0.5" onClick={() => { setIsNew(true); setSel(null); setDraft({ ...EMPTY, id: `CAM-0${cams.length + 1}` }); setMsg(null) }}>
            <Plus size={12} /> Add camera
          </button>
        }
        bodyClassName="overflow-auto"
      >
        <table className="w-full text-[12px]">
          <thead className="bg-ink-800/60 text-[11px] uppercase tracking-wider text-txt-dim">
            <tr>
              {['ID', 'Name', 'Approach', 'Stream', 'Proc.', 'Status', 'Feed', 'Last seen'].map((h) => (
                <th key={h} className="px-3 py-2 text-left font-normal">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {cams.map((c) => (
              <tr key={c.id} onClick={() => pick(c)} className={`cursor-pointer border-t border-line-soft/60 hover:bg-ink-800/60 ${sel === c.id ? 'bg-[#1d5fc4]/30' : ''}`}>
                <td className="num whitespace-nowrap px-3 py-2 text-white">{c.id}</td>
                <td className="whitespace-nowrap px-3">{c.name}</td>
                <td className="px-3">{APPROACH_LABEL[c.approach]}</td>
                <td className="max-w-[160px] truncate px-3 text-txt-dim" title={c.stream_url}>{c.stream_url || '—'}</td>
                <td className="num whitespace-nowrap px-3 text-txt-dim">{c.processing_width}px · {c.processing_fps}fps</td>
                <td className="whitespace-nowrap px-3" title={c.detail}><StatusDot state={HEALTH[c.status]} /> {c.status.replace('_', ' ')}{c.is_sample && <span className="ml-1 text-[9px] font-semibold text-warn">SAMPLE</span>}</td>
                <td className="num whitespace-nowrap px-3 text-txt-dim">{c.status === 'online' ? `${c.camera_fps.toFixed(0)} fps${c.resolution ? ` · ${c.resolution[0]}×${c.resolution[1]}` : ''}` : '—'}</td>
                <td className="num whitespace-nowrap px-3 text-txt-dim">{c.last_seen ? clockSec(c.last_seen) : 'never'}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="space-y-1 p-3 text-[11px] leading-relaxed text-txt-mute">
          <p>Each enabled camera has its own receiver thread that reconnects automatically (1 s → 30 s back-off); one failing phone never affects the others. Status comes from the receiver and is never faked.</p>
          <p>Hover a status to see its detail. Selected camera: <span className="text-txt">{sel ?? '—'}</span>{sel && cams.find((c) => c.id === sel)?.detail ? ` — ${cams.find((c) => c.id === sel)!.detail}` : ''}</p>
        </div>
      </Panel>

      <Panel title={isNew ? 'New Camera' : `Edit ${sel ?? ''}`} bodyClassName="p-3 space-y-3 overflow-auto">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Camera ID">
            <input className="input" value={draft.id} disabled={!isNew} onChange={(e) => set('id', e.target.value)} />
          </Field>
          <Field label="Approach">
            <select className="input" value={draft.approach} onChange={(e) => set('approach', e.target.value as Approach)}>
              {APPROACHES.map((a) => <option key={a} value={a}>{APPROACH_LABEL[a]}</option>)}
            </select>
          </Field>
        </div>
        <Field label="Name">
          <input className="input" value={draft.name} onChange={(e) => set('name', e.target.value)} />
        </Field>
        <Field label="Stream address (RTSP / HTTP)">
          <input className="input font-mono" placeholder="rtsp://192.168.137.21:8080/h264_ulaw.sdp" value={draft.stream_url} onChange={(e) => set('stream_url', e.target.value)} />
        </Field>
        <p className="-mt-2 text-[10px] leading-relaxed text-txt-mute">
          Phone: rtsp://… or http://…/video (MJPEG). Sample footage for testing: <span className="font-mono">file://samples/synthetic_approach.mp4</span> — always labelled SAMPLE.
        </p>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Processing width (px)">
            <input type="number" min={160} max={1920} step={32} className="input num" value={draft.processing_width} onChange={(e) => set('processing_width', Number(e.target.value))} />
          </Field>
          <Field label="Processing rate (fps)">
            <input type="number" min={0.5} max={30} step={0.5} className="input num" value={draft.processing_fps} onChange={(e) => set('processing_fps', Number(e.target.value))} />
          </Field>
        </div>
        <label className="flex items-center gap-2 text-[12px]">
          <input type="checkbox" checked={draft.enabled} onChange={(e) => set('enabled', e.target.checked)} /> Enabled
        </label>
        <div className="flex gap-2 pt-1">
          <button className="btn btn-primary" disabled={busy || !draft.id || !draft.name} onClick={save}>
            <Save size={12} /> Save
          </button>
          {!isNew && sel && (
            <button className="btn" onClick={reconnect} title="Restart this camera's receiver">
              <RefreshCw size={12} /> Reconnect
            </button>
          )}
          {!isNew && sel && (
            <button className="btn hover:border-crit hover:text-crit" onClick={remove}>
              <Trash2 size={12} /> Delete
            </button>
          )}
        </div>
        {msg && <div className={`text-[12px] ${msg.ok ? 'text-ok' : 'text-crit'}`}>{msg.text}</div>}
        <div className="border-t border-line-soft pt-3 text-[11px] leading-relaxed text-txt-mute">
          Each phone app exposes a different address — copy it from the app's screen. Credentials in the URL are masked when
          shown; saving the masked value keeps the stored one. Phones and laptop must be on the same Wi-Fi or the laptop hotspot.
        </div>
      </Panel>

      {!isNew && sel && (
        <Panel title={`Detection Regions · ${sel}`} className="2xl:col-span-2" bodyClassName="p-3 grid gap-4 lg:grid-cols-[minmax(0,1.4fr)_1fr]">
          <RegionEditor cameraId={sel} online={cams.find((c) => c.id === sel)?.status === 'online'} />
          <div className="space-y-2 text-[11px] leading-relaxed text-txt-dim">
            <p className="text-[12px] text-white">How the regions are used</p>
            <p>Each vehicle is tracked with a persistent ID (ByteTrack), so it is counted once — not once per frame.</p>
            <p><span className="text-sky-accent">Arrival</span>: first time a tracked vehicle is inside the approach or queue area (after 3 consecutive sightings).</p>
            <p><span className="text-warn">Queued</span>: inside the queue area and almost stationary; its waiting time runs from that moment until it crosses the stop line.</p>
            <p><span className="text-crit">Departure</span>: crossing the stop line away from the queue side.</p>
            <p>Pedestrians are detected and shown separately; they are never counted as vehicles.</p>
            <p>Position the phone high and looking along the approach so queued vehicles do not hide each other.</p>
          </div>
        </Panel>
      )}
    </PageGrid>
  )
}
