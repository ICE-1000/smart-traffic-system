import { useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, ComposedChart, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useLiveData } from '../../hooks/useLiveData'
import { APPROACH_COLOUR, APPROACH_LABEL, clock } from '../../lib/format'
import { bucketSeries, CHART } from '../../lib/series'
import { APPROACHES } from '../../types/traffic'
import { Panel, SimBadge, Waiting } from '../Panel'

type Tab = 'flow' | 'queue' | 'share'
const TABS: { id: Tab; label: string }[] = [
  { id: 'flow', label: 'Flow' },
  { id: 'queue', label: 'Queues' },
  { id: 'share', label: 'Green %' },
]

/** "Flow" panel (top right of the reference): bars + rate lines, three views. */
export function FlowPanel({ className = '' }: { className?: string }) {
  const { series, snapshot } = useLiveData()
  const [tab, setTab] = useState<Tab>('flow')
  const data = useMemo(() => bucketSeries(series, 30), [series])

  const share = useMemo(() => {
    if (!snapshot) return []
    const s = snapshot.signal.served_seconds
    const total = Object.values(s).reduce((a, b) => a + b, 0) || 1
    return APPROACHES.map((a) => ({ name: APPROACH_LABEL[a], approach: a, pct: Math.round((s[a] / total) * 1000) / 10, secs: s[a] }))
  }, [snapshot])

  return (
    <Panel
      className={className}
      title={
        <>
          Traffic Flow <SimBadge label="Sim" />
        </>
      }
      actions={TABS.map((t) => (
        <button key={t.id} className={`tab ${tab === t.id ? 'tab-active' : ''}`} onClick={() => setTab(t.id)}>
          {t.label}
        </button>
      ))}
      bodyClassName="p-2"
    >
      {data.length < 2 ? (
        <Waiting text="Collecting data…" />
      ) : (
        <ResponsiveContainer width="100%" height="100%">
          {tab === 'flow' ? (
            <ComposedChart data={data} margin={{ top: 8, right: -4, bottom: 0, left: -18 }}>
              <CartesianGrid stroke={CHART.grid} strokeDasharray="2 4" vertical={false} />
              <XAxis dataKey="ts" tickFormatter={clock} tick={CHART.tick} stroke={CHART.axis} minTickGap={30} />
              <YAxis yAxisId="l" tick={CHART.tick} stroke={CHART.axis} />
              <YAxis yAxisId="r" orientation="right" tick={CHART.tick} stroke={CHART.axis} width={28} />
              <Tooltip {...CHART.tooltip} labelFormatter={(v) => clock(Number(v))} />
              <Legend iconSize={8} wrapperStyle={{ fontSize: 10, top: -2 }} verticalAlign="top" align="left" />
              <Bar yAxisId="l" dataKey="in_view" name="Vehicles in view" fill="#2a9d8f" fillOpacity={0.55} isAnimationActive={false} />
              <Line yAxisId="r" dataKey="arrivals" name="Arrivals (veh/min)" stroke="#ffc23d" dot={false} strokeWidth={1.8} isAnimationActive={false} />
              <Line yAxisId="r" dataKey="departures" name="Departures (veh/min)" stroke="#3cc4ff" dot={false} strokeWidth={1.8} isAnimationActive={false} />
            </ComposedChart>
          ) : tab === 'queue' ? (
            <LineChart data={data} margin={{ top: 4, right: 6, bottom: 0, left: -18 }}>
              <CartesianGrid stroke={CHART.grid} strokeDasharray="2 4" vertical={false} />
              <XAxis dataKey="ts" tickFormatter={clock} tick={CHART.tick} stroke={CHART.axis} minTickGap={30} />
              <YAxis tick={CHART.tick} stroke={CHART.axis} />
              <Tooltip {...CHART.tooltip} labelFormatter={(v) => clock(Number(v))} />
              <Legend iconSize={8} wrapperStyle={{ fontSize: 10, top: -2 }} verticalAlign="top" align="left" />
              {APPROACHES.map((a) => (
                <Line key={a} dataKey={`${a}_queue`} name={APPROACH_LABEL[a]} stroke={APPROACH_COLOUR[a]} dot={false} strokeWidth={1.6} isAnimationActive={false} />
              ))}
            </LineChart>
          ) : (
            <BarChart data={share} margin={{ top: 12, right: 6, bottom: 0, left: -18 }}>
              <CartesianGrid stroke={CHART.grid} strokeDasharray="2 4" vertical={false} />
              <XAxis dataKey="name" tick={CHART.tick} stroke={CHART.axis} />
              <YAxis tick={CHART.tick} stroke={CHART.axis} unit="%" />
              <Tooltip {...CHART.tooltip} formatter={(v, _n, item) => [`${v}% (${Math.round((item.payload as { secs: number }).secs)}s)`, 'Simulated green']} />
              <Bar dataKey="pct" name="Green share" isAnimationActive={false} fill="#3cc4ff" />
            </BarChart>
          )}
        </ResponsiveContainer>
      )}
    </Panel>
  )
}
