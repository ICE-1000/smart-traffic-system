import type { ReactNode } from 'react'
import { useLiveData } from '../hooks/useLiveData'

interface PanelProps {
  title: ReactNode
  actions?: ReactNode
  children: ReactNode
  className?: string
  bodyClassName?: string
}

/** Standard control-room panel: gradient title strip + bordered body. */
export function Panel({ title, actions, children, className = '', bodyClassName = '' }: PanelProps) {
  return (
    <section className={`panel panel-corners flex min-h-0 flex-col ${className}`}>
      <header className="panel-head shrink-0">
        <span className="flex min-w-0 items-center gap-2 whitespace-nowrap">{title}</span>
        {actions && <div className="flex items-center gap-1">{actions}</div>}
      </header>
      <div className={`min-h-0 flex-1 ${bodyClassName}`}>{children}</div>
    </section>
  )
}

/** Shown wherever some values come from the demo model rather than cameras. */
export function SimBadge({ label }: { label?: string }) {
  const { snapshot } = useLiveData()
  if (!snapshot || snapshot.source === 'vision' || snapshot.source === 'none') return null
  const partial = snapshot.source === 'mixed' && snapshot.demo !== null
  if (snapshot.source === 'mixed' && !partial) return null
  return (
    <span className="sim-badge" title={partial ? 'Some approaches use the demo traffic model because their camera is not delivering data' : 'Values come from the demo traffic model, not from cameras'}>
      {label ?? (partial ? 'Partly simulated' : 'Simulated')}
    </span>
  )
}

export function Waiting({ text = 'Waiting for backend…' }: { text?: string }) {
  return <div className="grid h-full place-items-center p-6 text-[12px] text-txt-dim">{text}</div>
}
