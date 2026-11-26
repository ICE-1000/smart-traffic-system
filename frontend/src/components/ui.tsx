import type { ReactNode } from 'react'
import { CATEGORY_COLOUR, CATEGORY_LABEL } from '../lib/format'
import type { CongestionCategory } from '../types/traffic'

export type Health = 'ok' | 'warn' | 'error' | 'idle'
const DOT: Record<Health, string> = { ok: 'bg-ok', warn: 'bg-warn', error: 'bg-crit', idle: 'bg-txt-mute' }

export function StatusRow({ label, state, value, hint }: { label: string; state: Health; value: ReactNode; hint?: string }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-line-soft/50 py-2 last:border-0" title={hint}>
      <span className="flex items-center gap-2 text-txt">
        <span className={`h-2 w-2 rounded-full ${DOT[state]} ${state === 'ok' ? 'shadow-[0_0_6px_#2ed47a]' : ''}`} />
        {label}
      </span>
      <span className="num text-right text-[12px] text-txt-dim">{value}</span>
    </div>
  )
}

export function StatusDot({ state }: { state: Health }) {
  return <span className={`mr-1 inline-block h-2 w-2 rounded-full ${DOT[state]}`} />
}

export function CategoryTag({ category }: { category: CongestionCategory }) {
  const c = CATEGORY_COLOUR[category]
  return (
    <span className="inline-block whitespace-nowrap border px-1.5 text-[10px] font-semibold uppercase tracking-wider" style={{ color: c, borderColor: `${c}88`, background: `${c}14` }}>
      {CATEGORY_LABEL[category]}
    </span>
  )
}

export function ScoreBar({ value, colour, max = 100 }: { value: number; colour: string; max?: number }) {
  return (
    <div className="h-2.5 w-full bg-ink-950/80 outline outline-1 outline-line-soft">
      <div className="h-full transition-[width] duration-500" style={{ width: `${Math.min(100, (value / max) * 100)}%`, background: colour }} />
    </div>
  )
}

export function PageGrid({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div className="absolute inset-0 overflow-y-auto">
      <div className={`p-3 ${className}`}>{children}</div>
    </div>
  )
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      {children}
    </label>
  )
}
