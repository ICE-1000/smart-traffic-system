import { ArrowRight } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Panel, SimBadge, Waiting } from '../components/Panel'
import { SignalHead } from '../components/SignalHead'
import { PageGrid, ScoreBar } from '../components/ui'
import { useLiveData } from '../hooks/useLiveData'
import { APPROACH_COLOUR, APPROACH_LABEL, clockSec, secs } from '../lib/format'
import { api } from '../services/api'
import type { Approach } from '../types/traffic'

interface LogRow {
  ts: number
  recommended: Approach | null
  next_recommended: Approach | null
  rule: string
  reason: string
  source: string
}
const RULE: Record<string, string> = {
  demand: 'Highest demand',
  starvation: 'Fairness (starvation guard)',
  max_skip: 'Service check',
  no_data: 'No data — fixed-time fallback',
  no_demand: 'No demand — hold',
}

export function PriorityPage() {
  const { snapshot } = useLiveData()
  const [log, setLog] = useState<LogRow[]>([])

  useEffect(() => {
    const load = () => api.get<LogRow[]>('/api/priority/history?limit=40').then(setLog).catch(() => undefined)
    load()
    const t = window.setInterval(load, 5000)
    return () => window.clearInterval(t)
  }, [])

  if (!snapshot) return <Waiting />
  const p = snapshot.priority
  const rec = p.recommended ? snapshot.approaches[p.recommended] : null
  const maxIdx = Math.max(1, ...p.ranking.map((r) => r.priority_index))

  return (
    <PageGrid className="grid gap-3 xl:grid-cols-[1fr_1.2fr]">
      <div className="flex flex-col gap-3">
        <Panel title={<>Current Priority Decision <SimBadge /></>} bodyClassName="p-4">
          <div className="flex items-center gap-4">
            <div>
              <div className="label">Prioritised approach</div>
              <div className="num text-[34px] font-semibold leading-none" style={{ color: p.recommended ? APPROACH_COLOUR[p.recommended] : '#8fa6c9' }}>
                {p.recommended ? APPROACH_LABEL[p.recommended] : 'None'}
              </div>
            </div>
            <ArrowRight className="text-txt-mute" />
            <div>
              <div className="label">Next recommended</div>
              <div className="num text-[22px] text-white">{p.next_recommended ? APPROACH_LABEL[p.next_recommended] : '—'}</div>
            </div>
            <div className="ml-auto text-right">
              <div className="label">Rule</div>
              <div className="text-[12px] text-sky-accent">{RULE[p.rule]}</div>
            </div>
          </div>
          <div className="mt-4 grid grid-cols-3 gap-3 border-y border-line-soft py-3">
            <Kv k="Congestion score" v={rec ? rec.congestion.score.toFixed(0) : '—'} />
            <Kv k="Average wait" v={rec ? secs(rec.measurement.avg_wait_s) : '—'} />
            <Kv k="Unserved for" v={rec ? secs(rec.time_since_served_s) : '—'} />
          </div>
          <div className="mt-3">
            <div className="label">Reason (generated from measurements)</div>
            <p className="text-[13px] leading-relaxed text-white">{p.reason}</p>
          </div>
          <div className="mt-3 flex items-center gap-2 text-[11px] text-txt-dim">
            Simulated signal now: <SignalHead colour={snapshot.signal.colours[snapshot.signal.current]} size={7} horizontal />
            {APPROACH_LABEL[snapshot.signal.current]} · {snapshot.signal.stage.replace('_', '-')}
          </div>
        </Panel>

        <Panel title="Priority Ranking" bodyClassName="p-3 space-y-2.5">
          {p.ranking.map((r) => (
            <div key={r.approach} className={r.eligible ? '' : 'opacity-50'}>
              <div className="mb-1 flex justify-between text-[11px]">
                <span className="text-white">{APPROACH_LABEL[r.approach]} <span className="text-txt-dim">· {r.note}</span></span>
                <span className="num text-white">{r.priority_index.toFixed(0)}</span>
              </div>
              <ScoreBar value={r.priority_index} max={maxIdx} colour={APPROACH_COLOUR[r.approach]} />
              <div className="num mt-0.5 flex gap-4 text-[10px] text-txt-mute">
                <span>score {r.congestion_score.toFixed(0)}</span>
                <span>queue {r.queue_count}</span>
                <span>wait {secs(r.avg_wait_s)}</span>
                <span>unserved {secs(r.time_since_served_s)}</span>
              </div>
            </div>
          ))}
          <p className="pt-1 text-[10px] leading-relaxed text-txt-mute">
            Index = 0.7 × congestion score + 0.3 × 100 × min(unserved / starvation limit, 1). Approaches with no queue and no pedestrian call are
            skipped until they reach the max-skip time.
          </p>
        </Panel>
      </div>

      <Panel title="Decision Log" bodyClassName="overflow-auto">
        <table className="w-full text-[12px]">
          <thead className="sticky top-0 bg-ink-900 text-[11px] uppercase tracking-wider text-txt-dim">
            <tr>
              <th className="px-3 py-2 text-left font-normal">Time</th>
              <th className="px-3 text-left font-normal">Priority</th>
              <th className="px-3 text-left font-normal">Rule</th>
              <th className="px-3 text-left font-normal">Reason</th>
            </tr>
          </thead>
          <tbody>
            {log.map((r, i) => (
              <tr key={i} className="border-t border-line-soft/60 align-top">
                <td className="num whitespace-nowrap px-3 py-2 text-txt-dim">{clockSec(r.ts)}</td>
                <td className="px-3 py-2" style={{ color: r.recommended ? APPROACH_COLOUR[r.recommended] : undefined }}>{r.recommended ? APPROACH_LABEL[r.recommended] : '—'}</td>
                <td className="whitespace-nowrap px-3 py-2 text-txt-dim">{RULE[r.rule] ?? r.rule}</td>
                <td className="px-3 py-2 text-[11px] leading-relaxed">{r.reason}{(r.source === 'demo' || r.source === 'mixed') && <span className="ml-1 text-[9px] font-semibold text-warn">{r.source === 'demo' ? 'SIM' : 'MIXED'}</span>}</td>
              </tr>
            ))}
            {log.length === 0 && (
              <tr><td colSpan={4} className="p-4 text-txt-dim">No decisions stored yet.</td></tr>
            )}
          </tbody>
        </table>
      </Panel>
    </PageGrid>
  )
}

function Kv({ k, v }: { k: string; v: string }) {
  return (
    <div>
      <div className="text-[11px] text-txt-dim">{k}</div>
      <div className="num text-[20px] text-num">{v}</div>
    </div>
  )
}
