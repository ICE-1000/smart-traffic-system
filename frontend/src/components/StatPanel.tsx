import type { ReactNode } from 'react'

interface Sub {
  label: string
  value: ReactNode
}

/** Compact KPI box: title, one large value, two sub-values (reference layout). */
export function StatPanel({ title, value, unit, subs, valueClass = '' }: { title: string; value: ReactNode; unit?: string; subs: Sub[]; valueClass?: string }) {
  return (
    <div className="panel panel-corners px-3 pb-2 pt-1.5">
      <div className="stat-title">{title}</div>
      <div className="mt-1.5 flex items-end gap-5">
        <div className={`num text-[30px] font-semibold leading-none text-num ${valueClass}`}>
          {value}
          {unit && <span className="ml-1 text-[12px] font-normal text-txt-dim">{unit}</span>}
        </div>
        {subs.map((s) => (
          <div key={s.label} className="text-center leading-tight">
            <div className="text-[11px] text-white">{s.label}</div>
            <div className="num mt-0.5 text-[16px] text-num">{s.value}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
