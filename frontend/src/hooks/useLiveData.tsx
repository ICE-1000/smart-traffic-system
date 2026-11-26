import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { api, wsUrl } from '../services/api'
import type { SeriesPoint, Snapshot } from '../types/traffic'

export type WsStatus = 'connecting' | 'open' | 'closed'

interface LiveData {
  snapshot: Snapshot | null
  series: SeriesPoint[]
  wsStatus: WsStatus
  lastMessageAt: number | null
}

const MAX_POINTS = 900 // 15 min at 1 Hz
const LiveContext = createContext<LiveData>({ snapshot: null, series: [], wsStatus: 'connecting', lastMessageAt: null })

/** One WebSocket for the whole app, with exponential reconnect back-off. */
export function LiveDataProvider({ children }: { children: ReactNode }) {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null)
  const [series, setSeries] = useState<SeriesPoint[]>([])
  const [wsStatus, setWsStatus] = useState<WsStatus>('connecting')
  const [lastMessageAt, setLastMessageAt] = useState<number | null>(null)
  const retry = useRef(0)

  useEffect(() => {
    let ws: WebSocket | null = null
    let timer: number | undefined
    let disposed = false

    const seed = () =>
      api
        .get<{ points: SeriesPoint[] }>('/api/traffic/recent?seconds=900')
        .then((r) => setSeries(r.points.slice(-MAX_POINTS)))
        .catch(() => undefined)

    const connect = () => {
      setWsStatus('connecting')
      ws = new WebSocket(wsUrl('/ws/live'))
      ws.onopen = () => {
        retry.current = 0
        setWsStatus('open')
        seed()
      }
      ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data)
        if (msg.type !== 'snapshot') return
        setSnapshot(msg as Snapshot)
        setLastMessageAt(Date.now())
        setSeries((prev) => {
          const p = (msg as Snapshot).point
          if (prev.length && prev[prev.length - 1].ts >= p.ts) return prev
          const next = prev.length >= MAX_POINTS ? prev.slice(prev.length - MAX_POINTS + 1) : prev.slice()
          next.push(p)
          return next
        })
      }
      ws.onclose = () => {
        if (disposed) return
        setWsStatus('closed')
        const delay = Math.min(10000, 500 * 2 ** retry.current++)
        timer = window.setTimeout(connect, delay)
      }
      ws.onerror = () => ws?.close()
    }
    connect()
    // keep-alive so intermediaries don't drop an idle socket
    const ping = window.setInterval(() => ws?.readyState === WebSocket.OPEN && ws.send('ping'), 20000)
    return () => {
      disposed = true
      window.clearTimeout(timer)
      window.clearInterval(ping)
      ws?.close()
    }
  }, [])

  return <LiveContext.Provider value={{ snapshot, series, wsStatus, lastMessageAt }}>{children}</LiveContext.Provider>
}

export const useLiveData = () => useContext(LiveContext)
