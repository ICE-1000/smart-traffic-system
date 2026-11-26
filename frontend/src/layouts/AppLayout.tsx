import { Expand, Menu, Shrink } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import type { PageId } from '../hooks/useHashRoute'
import { PAGE_TRAIL, Sidebar } from './Sidebar'
import { TopBar } from './TopBar'

interface Props {
  page: PageId
  onNavigate: (p: PageId) => void
  children: ReactNode
}

export function AppLayout({ page, onNavigate, children }: Props) {
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem('nav-collapsed') === '1')
  const [fullscreen, setFullscreen] = useState(false)

  useEffect(() => {
    try {
      localStorage.setItem('nav-collapsed', collapsed ? '1' : '0')
    } catch {
      /* storage unavailable */
    }
  }, [collapsed])
  useEffect(() => {
    const on = () => setFullscreen(Boolean(document.fullscreenElement))
    document.addEventListener('fullscreenchange', on)
    return () => document.removeEventListener('fullscreenchange', on)
  }, [])

  const toggleFullscreen = () =>
    document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen().catch(() => undefined)

  const trail = PAGE_TRAIL[page]
  return (
    <div className="flex h-full flex-col">
      <TopBar />
      <div className="flex min-h-0 flex-1">
        <Sidebar page={page} onNavigate={onNavigate} collapsed={collapsed} onToggle={() => setCollapsed((c) => !c)} />
        <main className="flex min-w-0 flex-1 flex-col">
          {/* Breadcrumb strip — light bar as in the reference layout */}
          <div className="flex h-8 shrink-0 items-center justify-between border-b border-[#c9d6ea] bg-[#f4f7fc] px-3 text-[12px] text-[#5b6b85]">
            <div className="flex items-center gap-3">
              <button onClick={() => setCollapsed((c) => !c)} title="Toggle navigation" className="text-[#33445f] hover:text-[#1565c0]">
                <Menu size={15} />
              </button>
              <nav className="flex items-center gap-1.5">
                {trail.map((t, i) => (
                  <span key={t} className="flex items-center gap-1.5">
                    {i > 0 && <span className="text-[#a5b2c6]">/</span>}
                    <span className={i === trail.length - 1 ? 'font-medium text-[#1d2b44]' : ''}>{t}</span>
                  </span>
                ))}
              </nav>
            </div>
            <button onClick={toggleFullscreen} title={fullscreen ? 'Exit full screen' : 'Full screen'} className="text-[#33445f] hover:text-[#1565c0]">
              {fullscreen ? <Shrink size={15} /> : <Expand size={15} />}
            </button>
          </div>
          <div className="relative min-h-0 flex-1 overflow-hidden bg-ink-850">{children}</div>
        </main>
      </div>
    </div>
  )
}
