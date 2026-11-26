import { Bell, ChevronDown, User } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useLiveData } from '../hooks/useLiveData'
import { clockSec } from '../lib/format'

function useNow() {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(t)
  }, [])
  return now
}

export function TopBar() {
  const now = useNow()
  const { snapshot, wsStatus, lastMessageAt } = useLiveData()
  const [bellOpen, setBellOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const close = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setBellOpen(false)
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  const stale = lastMessageAt !== null && now - lastMessageAt > 5000
  const status =
    wsStatus !== 'open' ? { t: 'Backend offline', c: 'bg-crit' } : stale ? { t: 'Data stale', c: 'bg-warn' } : { t: 'Operational', c: 'bg-ok' }

  // Notifications are derived from live state — nothing is invented.
  const alerts: { level: 'warn' | 'crit'; text: string }[] = []
  if (wsStatus !== 'open') alerts.push({ level: 'crit', text: 'No connection to the processing backend' })
  if (snapshot) {
    for (const i of snapshot.incidents) alerts.push({ level: i.severity === 'critical' ? 'crit' : 'warn', text: i.message })
    for (const c of snapshot.cameras)
      if (c.status !== 'online' && c.has_stream_url && c.enabled && !snapshot.incidents.some((i) => i.key === `camera_failure:${c.id}`))
        alerts.push({ level: 'warn', text: `${c.id} ${c.name}: ${c.detail}` })
    for (const a of Object.values(snapshot.approaches))
      if (a.congestion.category === 'critical')
        alerts.push({ level: 'crit', text: `Critical congestion on ${a.approach} approach (score ${a.congestion.score.toFixed(0)})` })
  }

  const d = new Date(now)
  return (
    <header className="flex h-12 shrink-0 items-center justify-between border-b border-line-soft bg-ink-950 px-4">
      <div className="flex items-center gap-3">
        <div className="flex items-baseline gap-1.5 select-none" title="Smart Traffic Management and Intelligent Transportation System for Lusaka CBD">
          <span className="font-din text-[22px] font-bold italic tracking-wide text-white">SMART TRAFFIC</span>
          <span className="font-din text-[22px] font-bold italic tracking-wide text-sky-accent">ITS</span>
        </div>
        <span className="hidden border-l border-line-soft pl-3 text-[11px] leading-tight text-txt-dim md:block">
          Smart Traffic Management and Intelligent
          <br />
          Transportation System for Lusaka CBD
        </span>
      </div>

      <div className="flex items-center gap-5 text-[12px]">
        <div className="hidden items-center gap-2 lg:flex">
          <span className={`h-2 w-2 rounded-full ${status.c}`} />
          <span className="text-txt-dim">{status.t}</span>
        </div>
        <div className="num hidden text-right leading-tight sm:block">
          <div className="text-[14px] text-white">{clockSec(now / 1000)}</div>
          <div className="text-[10px] text-txt-dim">
            {d.toLocaleDateString([], { weekday: 'short', day: '2-digit', month: 'short', year: 'numeric' })}
          </div>
        </div>
        <div className="relative" ref={ref}>
          <button onClick={() => setBellOpen((o) => !o)} className="relative grid h-8 w-8 place-items-center text-txt-dim hover:text-white" title="Notifications">
            <Bell size={17} />
            {alerts.length > 0 && (
              <span className="num absolute -right-0.5 -top-0.5 grid h-4 min-w-4 place-items-center rounded-full bg-crit px-1 text-[10px] text-white">
                {alerts.length}
              </span>
            )}
          </button>
          {bellOpen && (
            <div className="panel absolute right-0 top-10 z-50 w-80">
              <div className="panel-head">Notifications</div>
              <ul className="max-h-72 overflow-y-auto p-2">
                {alerts.length === 0 && <li className="p-2 text-txt-dim">No active alerts.</li>}
                {alerts.map((a, i) => (
                  <li key={i} className="flex gap-2 border-b border-line-soft/50 p-2 last:border-0">
                    <span className={`mt-1 h-2 w-2 shrink-0 rounded-full ${a.level === 'crit' ? 'bg-crit' : 'bg-warn'}`} />
                    <span className="text-[12px] text-txt">{a.text}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
        <div className="flex items-center gap-1.5 text-white">
          <User size={16} />
          <span>operator</span>
          <ChevronDown size={13} className="text-txt-dim" />
        </div>
      </div>
    </header>
  )
}
