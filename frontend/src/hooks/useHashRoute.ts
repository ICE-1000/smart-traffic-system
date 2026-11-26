import { useEffect, useState } from 'react'

export type PageId =
  | 'overview'
  | 'live'
  | 'cameras'
  | 'analytics'
  | 'congestion'
  | 'priority'
  | 'simulation'
  | 'evaluation'
  | 'incidents'
  | 'surveys'
  | 'settings'

const PAGES: PageId[] = [
  'overview', 'live', 'cameras', 'analytics', 'congestion', 'priority', 'simulation', 'evaluation', 'incidents', 'surveys', 'settings',
]

const read = (): PageId => {
  const h = location.hash.replace(/^#\/?/, '') as PageId
  return PAGES.includes(h) ? h : 'overview'
}

/** Minimal hash router — keeps deep links working without a router dependency. */
export function useHashRoute(): [PageId, (p: PageId) => void] {
  const [page, setPage] = useState<PageId>(read)
  useEffect(() => {
    const on = () => setPage(read())
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  return [page, (p) => (location.hash = `/${p}`)]
}
