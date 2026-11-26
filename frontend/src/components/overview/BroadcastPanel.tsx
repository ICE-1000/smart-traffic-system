import { BarChart3, ChevronLeft, ChevronRight } from 'lucide-react'
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import type { PageId } from '../../hooks/useHashRoute'
import { useLiveData } from '../../hooks/useLiveData'
import { APPROACH_LABEL, APPROACH_SHORT, clockSec } from '../../lib/format'
import { Panel, SimBadge, Waiting } from '../Panel'

const RULE_LABEL: Record<string, string> = {
  demand: 'Demand',
  starvation: 'Fairness',
  max_skip: 'Service check',
  no_data: 'No-data fallback',
  no_demand: 'Hold',
  incident: 'Check site',
}

/** "Congestion broadcast" carousel + congestion-analysis summary (bottom right of reference). */
export function BroadcastPanel({ className = '', onNavigate }: { className?: string; onNavigate: (p: PageId) => void }) {
  const { snapshot } = useLiveData()
  const [idx, setIdx] = useState(0)
  const [pinned, setPinned] = useState(false)

  // Items: the live recommendation followed by the reasons of recent phase starts.
  const items = useMemo(() => {
    if (!snapshot) return []
    const live = { ts: snapshot.ts, title: 'Live recommendation', rule: snapshot.priority.rule, text: snapshot.priority.reason }
    const past = snapshot.signal.events
      .filter((e) => e.kind === 'phase_start' && e.approach)
      .slice(0, 8)
      .map((e) => ({ ts: e.ts, title: `${APPROACH_LABEL[e.approach!]} green started`, rule: '', text: e.reason }))
    const incidents = snapshot.incidents.map((i) => ({
      ts: i.started,
      title: `${i.severity === 'critical' ? 'INCIDENT' : 'Alert'} · ${i.kind.replace('_', ' ')}`,
      rule: 'incident',
      text: i.message,
    }))
    return [...incidents, live, ...past]
  }, [snapshot])

  useEffect(() => {
    if (!pinned) setIdx(0)
  }, [items, pinned])

  if (!snapshot) return <Panel className={className} title="Congestion Broadcast"><Waiting /></Panel>

  const item = items[Math.min(idx, items.length - 1)]
  const t = snapshot.totals
  const worst = Object.values(snapshot.approaches).reduce((a, b) => (b.measurement.queue_count > a.measurement.queue_count ? b : a))
  const longest = Object.values(snapshot.approaches).reduce((a, b) => (b.measurement.queue_length_m > a.measurement.queue_length_m ? b : a))
  const go = (d: number) => {
    setPinned(true)
    setIdx((i) => (i + d + items.length) % items.length)
  }

  return (
    <Panel
      className={className}
      title={
        <>
          Congestion Broadcast <SimBadge />
        </>
      }
      bodyClassName="flex flex-col"
    >
      <div className="flex min-h-[96px] flex-1 items-stretch">
        <button onClick={() => go(1)} className="px-1.5 text-txt-dim hover:text-white" title="Older">
          <ChevronLeft size={16} />
        </button>
        <div className="min-w-0 flex-1 overflow-y-auto py-2">
          <div className="mb-1 flex items-center gap-2 text-[11px]">
            <span className={item.rule === 'incident' ? 'font-semibold text-crit' : 'text-sky-accent'}>{item.title}</span>
            {item.rule && <span className="border border-line px-1 text-[10px] text-txt-dim">{RULE_LABEL[item.rule]}</span>}
            <span className="num ml-auto text-txt-mute">{clockSec(item.ts)}</span>
          </div>
          <p className="text-[12px] leading-snug text-txt">{item.text}</p>
          <div className="mt-1 flex gap-1">
            {items.map((_, i) => (
              <span key={i} className={`h-1 w-3 ${i === idx ? 'bg-sky-accent' : 'bg-line-soft'}`} />
            ))}
          </div>
        </div>
        <button onClick={() => (idx === 0 ? setPinned(false) : go(-1))} className="px-1.5 text-txt-dim hover:text-white" title="Newer">
          <ChevronRight size={16} />
        </button>
      </div>

      <div className="shrink-0 border-t border-line-soft px-3 pb-1.5 pt-1">
        <div className="mb-1 text-[12px] font-semibold text-white">Congestion Analysis</div>
        <div className="grid grid-cols-2 gap-3 text-[11px]">
          <div>
            <div className="mb-1 flex items-center gap-2">
              <span className="whitespace-nowrap font-semibold text-num">Queue Overrun</span>
              <button className="btn px-1.5 py-0 text-[10px]" onClick={() => onNavigate('congestion')}>
                <BarChart3 size={10} /> Chart
              </button>
            </div>
            <Row k="Critical" v={t.critical_approaches || 'None'} />
            <Row k="Most queued" v={worst.measurement.queue_count ? `${APPROACH_SHORT[worst.approach]} · ${worst.measurement.queue_count} veh` : 'None'} />
            <Row k="Longest wait" v={`${Math.round(Math.max(...Object.values(snapshot.approaches).map((a) => a.measurement.max_wait_s)))} s`} />
          </div>
          <div>
            <div className="mb-1 flex items-center gap-2">
              <span className="font-semibold text-num">Spillback</span>
              <button className="btn px-1.5 py-0 text-[10px]" onClick={() => onNavigate('analytics')}>
                <BarChart3 size={10} /> Chart
              </button>
            </div>
            <Row k="At limit" v={t.spillback_approaches || 'None'} />
            <Row k="Longest" v={longest.measurement.queue_length_m ? `${APPROACH_SHORT[longest.approach]} · ${Math.round(longest.measurement.queue_length_m)} m` : 'None'} />
            <Row k="Queued now" v={`${t.queued} veh`} />
          </div>
        </div>
      </div>
    </Panel>
  )
}

function Row({ k, v }: { k: string; v: ReactNode }) {
  return (
    <div className="flex justify-between gap-2 whitespace-nowrap leading-[18px]">
      <span className="text-txt-dim">{k}:</span>
      <span className="num text-white">{v}</span>
    </div>
  )
}
