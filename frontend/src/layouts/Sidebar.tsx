import {
  AlertTriangle,
  Cctv,
  ClipboardList,
  ChartColumn,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Gauge,
  Scale,
  LayoutDashboard,
  ListOrdered,
  MonitorPlay,
  Settings,
  Signpost,
  TrafficCone,
  Waypoints,
  type LucideIcon,
} from 'lucide-react'
import { useState } from 'react'
import type { PageId } from '../hooks/useHashRoute'

interface Leaf {
  id: PageId
  label: string
  icon: LucideIcon
}
interface Group {
  key: string
  label: string
  icon: LucideIcon
  children: (Leaf | Group)[]
}
type Node = Leaf | Group
const isGroup = (n: Node): n is Group => 'children' in n

// Hierarchy mirrors the reference: a top "Smart Traffic" group with a nested
// "Intersection" group, then device / system sections.
export const NAV: Node[] = [
  {
    key: 'smart',
    label: 'Smart Traffic',
    icon: TrafficCone,
    children: [
      { id: 'overview', label: 'Overview', icon: LayoutDashboard },
      { id: 'live', label: 'Live Monitoring', icon: MonitorPlay },
      { id: 'incidents', label: 'Incidents & Alerts', icon: AlertTriangle },
      {
        key: 'intersection',
        label: 'Intersection',
        icon: Signpost,
        children: [
          { id: 'congestion', label: 'Congestion Analysis', icon: Gauge },
          { id: 'priority', label: 'Priority Decisions', icon: ListOrdered },
          { id: 'simulation', label: 'Signal Simulation', icon: Waypoints },
          { id: 'evaluation', label: 'Evaluation', icon: Scale },
        ],
      },
      { id: 'analytics', label: 'Traffic Analytics', icon: ChartColumn },
      { id: 'surveys', label: 'Field Surveys', icon: ClipboardList },
    ],
  },
  { id: 'cameras', label: 'Camera Management', icon: Cctv },
  { id: 'settings', label: 'System Settings', icon: Settings },
]

export const PAGE_TRAIL: Record<PageId, string[]> = {
  overview: ['Smart Traffic', 'Overview'],
  live: ['Smart Traffic', 'Live Monitoring'],
  congestion: ['Smart Traffic', 'Intersection', 'Congestion Analysis'],
  priority: ['Smart Traffic', 'Intersection', 'Priority Decisions'],
  simulation: ['Smart Traffic', 'Intersection', 'Signal Simulation'],
  evaluation: ['Smart Traffic', 'Intersection', 'Evaluation'],
  incidents: ['Smart Traffic', 'Incidents & Alerts'],
  surveys: ['Smart Traffic', 'Field Surveys'],
  analytics: ['Smart Traffic', 'Traffic Analytics'],
  cameras: ['Devices', 'Camera Management'],
  settings: ['System', 'System Settings'],
}

interface Props {
  page: PageId
  onNavigate: (p: PageId) => void
  collapsed: boolean
  onToggle: () => void
}

export function Sidebar({ page, onNavigate, collapsed, onToggle }: Props) {
  const [open, setOpen] = useState<Record<string, boolean>>({ smart: true, intersection: true })

  const render = (n: Node, depth: number) => {
    const pad = collapsed ? 0 : 14 + depth * 14
    if (isGroup(n)) {
      const isOpen = open[n.key] ?? true
      const Icon = n.icon
      return (
        <li key={n.key}>
          <button
            title={n.label}
            onClick={() => (collapsed ? onToggle() : setOpen((o) => ({ ...o, [n.key]: !isOpen })))}
            className={`flex h-9 w-full items-center gap-2 text-[13px] text-txt hover:bg-ink-800 ${collapsed ? 'justify-center' : ''}`}
            style={{ paddingLeft: pad }}
          >
            <Icon size={15} className="shrink-0 text-txt-dim" />
            {!collapsed && (
              <>
                <span className="flex-1 text-left">{n.label}</span>
                <ChevronDown size={13} className={`mr-3 text-txt-mute transition-transform ${isOpen ? '' : '-rotate-90'}`} />
              </>
            )}
          </button>
          {isOpen && !collapsed && <ul className={depth === 0 ? 'bg-ink-950/60' : ''}>{n.children.map((c) => render(c, depth + 1))}</ul>}
          {collapsed && <ul>{n.children.map((c) => render(c, depth + 1))}</ul>}
        </li>
      )
    }
    const Icon = n.icon
    const active = page === n.id
    return (
      <li key={n.id}>
        <button
          title={n.label}
          onClick={() => onNavigate(n.id)}
          aria-current={active ? 'page' : undefined}
          className={`flex h-9 w-full items-center gap-2 text-[13px] transition-colors ${collapsed ? 'justify-center' : ''} ${
            active ? 'bg-[#1d5fc4] text-white shadow-[inset_3px_0_0_#3cc4ff]' : 'text-txt-dim hover:bg-ink-800 hover:text-white'
          }`}
          style={{ paddingLeft: pad }}
        >
          <Icon size={15} className="shrink-0" />
          {!collapsed && <span className="truncate">{n.label}</span>}
        </button>
      </li>
    )
  }

  return (
    <aside
      className={`relative flex shrink-0 flex-col border-r border-line-soft bg-ink-900 transition-[width] duration-200 ${
        collapsed ? 'w-14' : 'w-[216px]'
      }`}
    >
      <nav className="flex-1 overflow-y-auto py-1">
        <ul>{NAV.map((n) => render(n, 0))}</ul>
      </nav>
      <div className="flex items-center justify-between px-3 pb-3">
        {!collapsed && <span className="num text-[10px] text-txt-mute">v1.1 · prototype</span>}
        <button
          onClick={onToggle}
          title={collapsed ? 'Expand navigation' : 'Collapse navigation'}
          className="grid h-7 w-7 place-items-center border border-line bg-ink-700 text-txt hover:border-sky-accent"
        >
          {collapsed ? <ChevronRight size={15} /> : <ChevronLeft size={15} />}
        </button>
      </div>
    </aside>
  )
}
