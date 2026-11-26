import { Eye, Search, Waypoints, X } from 'lucide-react'
import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { CameraPanel } from '../components/CameraPanel'
import { IntersectionMap, ROAD_HALF } from '../components/IntersectionMap'
import { BroadcastPanel } from '../components/overview/BroadcastPanel'
import { FlowPanel } from '../components/overview/FlowPanel'
import { QueuePanel } from '../components/overview/QueuePanel'
import { SignalHead } from '../components/SignalHead'
import { StatPanel } from '../components/StatPanel'
import type { PageId } from '../hooks/useHashRoute'
import { useLiveData } from '../hooks/useLiveData'
import { APPROACH_LABEL, secs } from '../lib/format'
import { api } from '../services/api'
import type { Approach, Site } from '../types/traffic'
import { APPROACHES } from '../types/traffic'

// Camera windows sit in the four quadrants around the junction, as in the reference.
const QUADRANT: Record<Approach, { h: 'left' | 'right'; v: 'top' | 'bottom' }> = {
  north: { h: 'left', v: 'top' },
  east: { h: 'right', v: 'top' },
  west: { h: 'left', v: 'bottom' },
  south: { h: 'right', v: 'bottom' },
}

function useStageSize<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [size, setSize] = useState({ w: 900, h: 700 })
  useEffect(() => {
    if (!ref.current) return
    const ro = new ResizeObserver(([e]) => setSize({ w: e.contentRect.width, h: e.contentRect.height }))
    ro.observe(ref.current)
    return () => ro.disconnect()
  }, [])
  return [ref, size] as const
}

function SourceBadge({ source, hasDemo }: { source: string; hasDemo: boolean }) {
  if (source === 'vision')
    return <span className="ml-2 self-center whitespace-nowrap border border-ok/60 bg-ok/10 px-1.5 py-px text-[10px] font-semibold uppercase tracking-wider text-ok">Camera + AI data</span>
  if (source === 'demo') return <span className="sim-badge ml-2 self-center whitespace-nowrap" title="Demo traffic model — no camera data">Simulated data · demo model</span>
  if (source === 'none') return <span className="sim-badge ml-2 self-center whitespace-nowrap">No camera data</span>
  return (
    <span className="sim-badge ml-2 self-center whitespace-nowrap" title="Approaches with a working camera use AI measurements; the others use the demo model or have no data">
      Mixed · {hasDemo ? 'partly simulated' : 'some approaches without data'}
    </span>
  )
}

export function OverviewPage({ onNavigate }: { onNavigate: (p: PageId) => void }) {
  const { snapshot } = useLiveData()
  const [hidden, setHidden] = useState<Set<Approach>>(new Set())
  const [showQueues, setShowQueues] = useState(true)
  const [planOpen, setPlanOpen] = useState(false)
  const [stageRef, stage] = useStageSize<HTMLDivElement>()

  const colW = Math.max(330, Math.min(430, stage.w * 0.27))
  const topPad = 132 // below selector + KPI panels
  const cx = (stage.w - colW - 8) / 2
  const cy = topPad + (stage.h - topPad) / 2
  const scale = Math.max(0.6, Math.min(1.15, (stage.h - topPad) / 760))
  const gap = (ROAD_HALF + 34) * scale
  // Window width: whatever fits in a quadrant, within sensible bounds.
  const winW = Math.max(200, Math.min(330, cx - gap - 12, (cy - topPad - gap - 50) * (16 / 9)))

  const [sites, setSites] = useState<Site[]>([])
  useEffect(() => {
    api.get<Site[]>('/api/sites').then(setSites).catch(() => undefined)
  }, [snapshot?.site.id])
  const switchSite = (id: string) => {
    const target = sites.find((x) => x.id === id)
    if (!target || id === snapshot?.site.id) return
    if (!confirm(`Switch the active study site to ${target.name}?\n\nMeasurements, surveys and evaluation runs from now on are recorded under this site. Move the phones to this site before switching.`)) return
    api.post('/api/sites/active', { id }).catch((e: Error) => alert(e.message))
  }

  const t = snapshot?.totals
  const cams = new Map(snapshot?.cameras.map((c) => [c.approach, c]) ?? [])

  return (
    <div ref={stageRef} className="absolute inset-0 overflow-hidden">
      <IntersectionMap snapshot={snapshot} showQueues={showQueues} scale={scale} cx={cx} cy={cy} extent={{ v: (cy - topPad) / scale, h: cx / scale }} />
      <div className="absolute inset-0">
        {APPROACHES.filter((a) => !hidden.has(a)).map((a) => {
          const q = QUADRANT[a]
          const cam = cams.get(a)
          const style: CSSProperties = { width: winW }
          if (q.h === 'left') style.right = stage.w - (cx - gap)
          else style.left = cx + gap
          if (q.v === 'top') style.bottom = stage.h - (cy - gap)
          else style.top = cy + gap
          return (
            <div key={a} className="absolute z-10" style={style}>
              <CameraPanel
                camera={cam}
                approach={snapshot?.approaches[a]}
                title={`${snapshot?.intersection.name ?? 'Intersection'} · ${APPROACH_LABEL[a]} approach`}
                onClose={() => setHidden((h) => new Set(h).add(a))}
                onMaximise={() => onNavigate('live')}
              />
            </div>
          )
        })}

        {/* top-left: intersection selector + KPI panels */}
        <div className="absolute left-3 top-3 z-20 flex flex-col gap-2">
          <div className="flex">
            <div className="flex h-7 w-[262px] items-center border border-line bg-ink-950/85 px-2 text-[12px] text-white">
              <select className="w-full bg-transparent outline-none" value={snapshot?.site.id ?? ''} onChange={(e) => switchSite(e.target.value)} aria-label="Study site">
                {sites.length === 0 && snapshot && <option value={snapshot.site.id}>{snapshot.site.name}</option>}
                {sites.map((x) => (
                  <option key={x.id} value={x.id} className="bg-ink-900">
                    {x.name}{x.corridor ? ` — ${x.corridor}` : ''}
                  </option>
                ))}
              </select>
            </div>
            <button className="grid h-7 w-8 place-items-center border border-l-0 border-line bg-[#1565c0] text-white" title="Select the study site (list on the left; manage sites in System Settings)">
              <Search size={13} />
            </button>
            {snapshot && <SourceBadge source={snapshot.source} hasDemo={snapshot.demo !== null} />}
            {snapshot && snapshot.site.node_type !== 'signalised' && (
              <span
                className="ml-1.5 self-center whitespace-nowrap border border-line bg-ink-950/85 px-1.5 py-px text-[10px] font-semibold uppercase tracking-wider text-txt-dim"
                title="Signal plan, priority and evaluation describe a hypothetical signalised operation of this site"
              >
                {snapshot.site.node_type === 'roundabout' ? 'Roundabout · signals hypothetical' : 'Control type unconfirmed'}
              </span>
            )}
          </div>
        </div>
        <div className="absolute left-3 top-[44px] z-20 flex gap-2">
          <StatPanel
            title="Vehicles Detected"
            value={t?.vehicles_detected ?? '—'}
            subs={[
              { label: 'Heavy', value: t?.heavy_in_view ?? '—' },
              { label: 'Light', value: t?.light_in_view ?? '—' },
            ]}
          />
          <StatPanel
            title="Most Congested"
            value={t ? APPROACH_LABEL[t.most_congested.approach] : '—'}
            valueClass="text-[24px]"
            subs={[
              { label: 'Avg wait', value: t ? secs(t.avg_wait_s) : '—' },
              { label: 'Feeds', value: t ? `${t.cameras_online}/${t.cameras_total}` : '—' },
            ]}
          />
        </div>

        {/* top-right of the map: view toggles (reference: two buttons) */}
        <div className="absolute top-3 z-20 flex gap-1.5" style={{ right: colW + 20 }}>
          <button className={`btn ${showQueues ? 'btn-primary' : ''}`} onClick={() => setShowQueues((s) => !s)} title="Show/hide queued-vehicle layer">
            <Eye size={13} /> Traffic Situation
          </button>
          <button className={`btn ${planOpen ? 'btn-primary' : ''}`} onClick={() => setPlanOpen((s) => !s)} title="Show the simulated signal plan">
            <Waypoints size={13} /> Signal Plan
          </button>
        </div>
        {hidden.size > 0 && (
          <button className="btn absolute bottom-3 left-3 z-20" onClick={() => setHidden(new Set())}>
            Restore {hidden.size} camera window{hidden.size > 1 ? 's' : ''}
          </button>
        )}
        {planOpen && snapshot && (
          <div className="panel panel-corners absolute top-12 z-30 w-[330px]" style={{ right: colW + 20 }}>
            <div className="panel-head">
              Signal Plan · simulation
              <button onClick={() => setPlanOpen(false)} className="text-txt-dim hover:text-white">
                <X size={14} />
              </button>
            </div>
            <div className="space-y-2 p-3 text-[12px]">
              <div className="flex items-center justify-between">
                <span className="text-txt-dim">Current</span>
                <span className="num text-white">
                  {APPROACH_LABEL[snapshot.signal.current]} · {snapshot.signal.stage.replace('_', '-')} {snapshot.signal.stage_elapsed_s.toFixed(0)}s
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-txt-dim">Min / max green</span>
                <span className="num text-white">
                  {snapshot.signal.config.min_green_s}s / {snapshot.signal.config.max_green_s}s
                </span>
              </div>
              <table className="w-full text-[11px]">
                <thead className="text-txt-dim">
                  <tr>
                    <th className="py-1 text-left font-normal">Approach</th>
                    <th className="text-center font-normal">Signal</th>
                    <th className="text-right font-normal">Index</th>
                    <th className="text-right font-normal">Unserved</th>
                  </tr>
                </thead>
                <tbody>
                  {APPROACHES.map((a) => {
                    const r = snapshot.priority.ranking.find((x) => x.approach === a)
                    return (
                      <tr key={a} className="border-t border-line-soft/60">
                        <td className="py-1">{APPROACH_LABEL[a]}</td>
                        <td className="text-center">
                          <SignalHead colour={snapshot.signal.colours[a]} size={7} horizontal />
                        </td>
                        <td className="num text-right">{r ? r.priority_index.toFixed(0) : '—'}</td>
                        <td className="num text-right">{secs(snapshot.signal.time_since_served_s[a])}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
              <button className="btn w-full justify-center" onClick={() => onNavigate('simulation')}>
                Open Signal Simulation
              </button>
            </div>
          </div>
        )}
      </div>

      {/* ---------------- right analytics column (floats over the map) ---------------- */}
      <div className="absolute bottom-2 right-2 top-2 z-20 flex flex-col gap-2" style={{ width: colW }}>
        <FlowPanel className="flex-1" />
        <QueuePanel className="flex-[0.9]" />
        <BroadcastPanel className="flex-[1.15]" onNavigate={onNavigate} />
      </div>
    </div>
  )
}
