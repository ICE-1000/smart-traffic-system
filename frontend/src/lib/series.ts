import type { SeriesPoint } from '../types/traffic'

/** Average 1 Hz points into fixed buckets (seconds) for compact charts. */
export function bucketSeries(points: SeriesPoint[], bucketS: number): SeriesPoint[] {
  const out: SeriesPoint[] = []
  let cur: { ts: number; n: number; sums: Record<string, number> } | null = null
  for (const p of points) {
    const b = Math.floor(p.ts / bucketS) * bucketS
    if (!cur || cur.ts !== b) {
      if (cur) out.push(finish(cur))
      cur = { ts: b, n: 0, sums: {} }
    }
    cur.n++
    for (const [k, v] of Object.entries(p)) if (k !== 'ts' && typeof v === 'number') cur.sums[k] = (cur.sums[k] ?? 0) + v
  }
  if (cur) out.push(finish(cur))
  return out
}

function finish(c: { ts: number; n: number; sums: Record<string, number> }): SeriesPoint {
  const row: Record<string, number> = { ts: c.ts }
  for (const [k, v] of Object.entries(c.sums)) row[k] = Math.round((v / c.n) * 10) / 10
  return row as SeriesPoint
}

export const CHART = {
  grid: '#173b70',
  axis: '#5f7aa3',
  tick: { fill: '#8fa6c9', fontSize: 10 },
  tooltip: {
    contentStyle: { background: '#081530', border: '1px solid #1d4f93', borderRadius: 0, fontSize: 11 },
    labelStyle: { color: '#8fa6c9' },
    itemStyle: { padding: 0 },
  },
}
