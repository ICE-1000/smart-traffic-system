import { useMemo } from 'react'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useLiveData } from '../../hooks/useLiveData'
import { clock } from '../../lib/format'
import { bucketSeries, CHART } from '../../lib/series'
import { APPROACHES } from '../../types/traffic'
import { DirectionGauge } from '../DirectionGauge'
import { Panel, SimBadge, Waiting } from '../Panel'

/** "Queue length" panel: total queue length over time + per-approach ring. */
export function QueuePanel({ className = '' }: { className?: string }) {
  const { series, snapshot } = useLiveData()
  const data = useMemo(
    () => bucketSeries(series, 20).map((p) => ({ ts: p.ts, qlen: Math.round(APPROACHES.reduce((s, a) => s + (p[`${a}_qlen`] ?? 0), 0)) })),
    [series],
  )
  const window = series.length ? `${clock(series[0].ts)} – ${clock(series[series.length - 1].ts)}` : ''
  return (
    <Panel
      className={className}
      title={
        <>
          Queue Length <SimBadge />
        </>
      }
      bodyClassName="flex p-2 gap-1"
    >
      <div className="min-w-0 flex-[1.4]">
        {data.length < 2 ? (
          <Waiting text="Collecting data…" />
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 10, right: 4, bottom: 0, left: -14 }}>
              <defs>
                <linearGradient id="qlenFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#6c8dff" stopOpacity={0.7} />
                  <stop offset="100%" stopColor="#6c8dff" stopOpacity={0.05} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke={CHART.grid} strokeDasharray="2 4" vertical={false} />
              <XAxis dataKey="ts" tickFormatter={clock} tick={CHART.tick} stroke={CHART.axis} minTickGap={24} />
              <YAxis tick={CHART.tick} stroke={CHART.axis} unit=" m" width={56} />
              <Tooltip {...CHART.tooltip} labelFormatter={(v) => clock(Number(v))} formatter={(v) => [`${v} m`, 'Total queue length']} />
              <Area dataKey="qlen" stroke="#8aa4ff" strokeWidth={1.5} fill="url(#qlenFill)" isAnimationActive={false} />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
      <div className="w-[150px] shrink-0">{snapshot ? <DirectionGauge approaches={snapshot.approaches} window={window} /> : <Waiting text="" />}</div>
    </Panel>
  )
}
