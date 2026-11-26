import { RefreshCw, RotateCcw, Save, Undo2 } from 'lucide-react'
import { useEffect, useRef, useState, type MouseEvent } from 'react'
import { api } from '../services/api'

type Pt = [number, number]
interface Regions {
  approach: Pt[]
  queue: Pt[]
  stop_line: Pt[] | null
  queue_length_m: number | null
  configured?: boolean
}
type Mode = 'approach' | 'queue' | 'stop_line'
const MODES: { id: Mode; label: string; hint: string; colour: string }[] = [
  { id: 'approach', label: 'Approach area', hint: 'Road leading to the junction — arrivals are counted when a vehicle enters it.', colour: '#3cc4ff' },
  { id: 'queue', label: 'Queue area', hint: 'Where vehicles stand waiting, ending at the stop line.', colour: '#ffb020' },
  { id: 'stop_line', label: 'Stop line', hint: 'Two points across the lanes. Crossing it counts a departure.', colour: '#ff4d4f' },
]

/**
 * Draw per-camera virtual regions on a live snapshot. Coordinates are stored
 * normalised (0..1) so they survive resolution changes.
 */
export function RegionEditor({ cameraId, online }: { cameraId: string; online: boolean }) {
  const [regions, setRegions] = useState<Regions | null>(null)
  const [mode, setMode] = useState<Mode>('queue')
  const [draft, setDraft] = useState<Pt[] | null>(null)
  const [imgT, setImgT] = useState(Date.now())
  const [imgOk, setImgOk] = useState(true)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const box = useRef<HTMLDivElement>(null)

  useEffect(() => {
    setDraft(null)
    setMsg(null)
    api.get<Regions>(`/api/cameras/${encodeURIComponent(cameraId)}/regions`).then(setRegions).catch(() => setRegions(null))
    setImgT(Date.now())
    setImgOk(true)
  }, [cameraId])

  if (!regions) return <div className="p-3 text-[12px] text-txt-dim">Loading regions…</div>

  const click = (e: MouseEvent) => {
    const r = box.current!.getBoundingClientRect()
    const p: Pt = [Math.round(((e.clientX - r.left) / r.width) * 1000) / 1000, Math.round(((e.clientY - r.top) / r.height) * 1000) / 1000]
    const next = [...(draft ?? []), p]
    if (mode === 'stop_line' && next.length === 2) {
      setRegions({ ...regions, stop_line: next })
      setDraft(null)
    } else setDraft(next)
  }
  const finish = () => {
    if (!draft) return
    if (mode !== 'stop_line' && draft.length >= 3) setRegions({ ...regions, [mode]: draft })
    setDraft(null)
  }
  const save = () =>
    api
      .put(`/api/cameras/${encodeURIComponent(cameraId)}/regions`, {
        approach: regions.approach,
        queue: regions.queue,
        stop_line: regions.stop_line,
        queue_length_m: regions.queue_length_m || null,
      })
      .then(() => setMsg({ ok: true, text: 'Regions saved — tracking uses them immediately.' }))
      .catch((e: Error) => setMsg({ ok: false, text: e.message }))

  const poly = (pts: Pt[]) => pts.map(([x, y]) => `${x * 100},${y * 100}`).join(' ')
  const cur = MODES.find((m) => m.id === mode)!

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-1">
        {MODES.map((m) => (
          <button key={m.id} className={`tab px-2 py-1 ${mode === m.id ? 'tab-active' : ''}`} onClick={() => { setMode(m.id); setDraft(null) }}>
            <span className="mr-1 inline-block h-2 w-2" style={{ background: m.colour }} />
            {m.label}
          </button>
        ))}
        <button className="btn ml-auto py-0.5" onClick={() => setImgT(Date.now())} title="Refresh snapshot">
          <RefreshCw size={11} />
        </button>
      </div>
      <p className="text-[11px] text-txt-dim">
        {cur.hint} {mode === 'stop_line' ? 'Click two points.' : 'Click to add points, then press Finish (3+ points).'}
      </p>
      <div ref={box} onClick={click} className="relative aspect-video w-full cursor-crosshair overflow-hidden border border-line bg-black">
        {online && imgOk ? (
          <img src={`/api/cameras/${encodeURIComponent(cameraId)}/snapshot.jpg?t=${imgT}`} onError={() => setImgOk(false)} className="h-full w-full object-fill" alt="Camera snapshot" draggable={false} />
        ) : (
          <div className="no-signal grid h-full place-items-center text-[11px] text-txt-mute">No snapshot (camera offline) — you can still draw</div>
        )}
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="pointer-events-none absolute inset-0 h-full w-full">
          <polygon points={poly(regions.approach)} fill="#3cc4ff" fillOpacity={0.08} stroke="#3cc4ff" strokeWidth={0.4} vectorEffect="non-scaling-stroke" />
          <polygon points={poly(regions.queue)} fill="#ffb020" fillOpacity={0.18} stroke="#ffb020" strokeWidth={0.6} vectorEffect="non-scaling-stroke" />
          {regions.stop_line && (
            <line x1={regions.stop_line[0][0] * 100} y1={regions.stop_line[0][1] * 100} x2={regions.stop_line[1][0] * 100} y2={regions.stop_line[1][1] * 100} stroke="#ff4d4f" strokeWidth={3} vectorEffect="non-scaling-stroke" />
          )}
          {draft && <polyline points={poly(draft)} fill="none" stroke="#fff" strokeDasharray="2 1" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />}
          {draft?.map(([x, y], i) => <circle key={i} cx={x * 100} cy={y * 100} r={0.8} fill="#fff" />)}
        </svg>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {mode !== 'stop_line' && (
          <button className="btn" disabled={!draft || draft.length < 3} onClick={finish}>
            Finish {cur.label.toLowerCase()}
          </button>
        )}
        <button className="btn" disabled={!draft?.length} onClick={() => setDraft((d) => (d && d.length > 1 ? d.slice(0, -1) : null))}>
          <Undo2 size={11} /> Undo point
        </button>
        {mode === 'stop_line' && regions.stop_line && (
          <button className="btn" onClick={() => setRegions({ ...regions, stop_line: null })}>Remove stop line</button>
        )}
        <button
          className="btn"
          onClick={() => setRegions({ approach: [[0, 0], [1, 0], [1, 1], [0, 1]], queue: [[0, 0.35], [1, 0.35], [1, 1], [0, 1]], stop_line: null, queue_length_m: null })}
        >
          <RotateCcw size={11} /> Defaults
        </button>
      </div>
      <label className="flex items-center gap-2 text-[12px]">
        <span className="text-txt-dim">Real length of queue area (m)</span>
        <input
          type="number"
          min={1}
          max={1000}
          className="input num w-24"
          value={regions.queue_length_m ?? ''}
          placeholder="optional"
          onChange={(e) => setRegions({ ...regions, queue_length_m: e.target.value ? Number(e.target.value) : null })}
        />
      </label>
      <p className="text-[10px] leading-relaxed text-txt-mute">
        With a stop line and a measured length, queue length is estimated from where the last waiting vehicle stands. Without them it is estimated from
        vehicle types (car 7 m, motorcycle 3.5 m, bus 14 m, truck 13 m incl. gaps), and departures are counted when a tracked vehicle leaves view.
      </p>
      <button className="btn btn-primary" onClick={save}>
        <Save size={12} /> Save regions
      </button>
      {msg && <div className={`text-[12px] ${msg.ok ? 'text-ok' : 'text-crit'}`}>{msg.text}</div>}
    </div>
  )
}
