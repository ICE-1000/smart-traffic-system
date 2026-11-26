import { APPROACH_SHORT, CATEGORY_COLOUR } from '../lib/format'
import type { Approach, ApproachState } from '../types/traffic'

const ANGLE: Record<Approach, number> = { north: -90, east: 0, south: 90, west: 180 }

function arc(cx: number, cy: number, r: number, a0: number, a1: number) {
  const p = (a: number) => [cx + r * Math.cos((a * Math.PI) / 180), cy + r * Math.sin((a * Math.PI) / 180)]
  const [x0, y0] = p(a0)
  const [x1, y1] = p(a1)
  return `M${x0} ${y0} A${r} ${r} 0 ${a1 - a0 > 180 ? 1 : 0} 1 ${x1} ${y1}`
}

/** Ring gauge: one segment per approach, coloured by congestion, labelled with queue count. */
export function DirectionGauge({ approaches, window }: { approaches: Record<Approach, ApproachState>; window: string }) {
  const cx = 80
  const cy = 100
  const r = 50
  return (
    <svg viewBox="0 0 160 184" className="h-full w-full">
      <text x={cx} y={11} textAnchor="middle" fontSize={11} className="fill-txt font-din">
        {window}
      </text>
      <circle cx={cx} cy={cy} r={r + 14} fill="none" stroke="#173b70" strokeWidth={1} />
      <circle cx={cx} cy={cy} r={r - 14} fill="none" stroke="#173b70" strokeWidth={1} />
      {(Object.keys(ANGLE) as Approach[]).map((a) => {
        const st = approaches[a]
        const c = ANGLE[a]
        const col = CATEGORY_COLOUR[st.congestion.category]
        const lx = cx + (r + 24) * Math.cos((c * Math.PI) / 180)
        const ly = cy + (r + 24) * Math.sin((c * Math.PI) / 180)
        const vx = cx + r * Math.cos((c * Math.PI) / 180)
        const vy = cy + r * Math.sin((c * Math.PI) / 180)
        return (
          <g key={a}>
            <path d={arc(cx, cy, r, c - 42, c + 42)} stroke={col} strokeWidth={16} fill="none" opacity={st.signal === 'green' ? 1 : 0.75} />
            {st.signal === 'green' && <path d={arc(cx, cy, r + 11, c - 42, c + 42)} stroke="#2ed47a" strokeWidth={2} fill="none" />}
            <text x={vx} y={vy + 3.5} textAnchor="middle" fontSize={10} fontWeight={700} className="font-din" fill="#06101f">
              {st.measurement.queue_count}
            </text>
            <text x={lx} y={ly + 4} textAnchor="middle" fontSize={11} className="fill-txt-dim">
              {APPROACH_SHORT[a]}
            </text>
          </g>
        )
      })}
      <text x={cx} y={cy - 2} textAnchor="middle" fontSize={18} className="fill-num font-din" fontWeight={600}>
        {Object.values(approaches).reduce((s, a) => s + a.measurement.queue_count, 0)}
      </text>
      <text x={cx} y={cy + 12} textAnchor="middle" fontSize={9} className="fill-txt-dim">
        queued
      </text>
    </svg>
  )
}
