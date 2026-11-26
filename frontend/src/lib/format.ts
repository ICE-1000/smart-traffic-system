import type { Approach, CongestionCategory, SignalColour } from '../types/traffic'

export const APPROACH_LABEL: Record<Approach, string> = { north: 'North', south: 'South', east: 'East', west: 'West' }
export const APPROACH_SHORT: Record<Approach, string> = { north: 'N', south: 'S', east: 'E', west: 'W' }
// One fixed hue per approach, reused by every chart.
export const APPROACH_COLOUR: Record<Approach, string> = {
  north: '#3cc4ff',
  south: '#a77bff',
  east: '#2ed47a',
  west: '#ff8a3d',
}

export const CATEGORY_COLOUR: Record<CongestionCategory, string> = {
  free: '#2ed47a',
  light: '#7bd96a',
  moderate: '#ffb020',
  heavy: '#ff7a2e',
  critical: '#ff4d4f',
}
export const CATEGORY_LABEL: Record<CongestionCategory, string> = {
  free: 'Free flow',
  light: 'Light',
  moderate: 'Moderate',
  heavy: 'Heavy',
  critical: 'Critical',
}

export const SIGNAL_COLOUR: Record<SignalColour, string> = { red: '#ff4d4f', yellow: '#ffb020', green: '#2ed47a' }

export const clock = (ts: number) =>
  new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })
export const clockSec = (ts: number) =>
  new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })

export const secs = (s: number) => (s >= 60 ? `${Math.floor(s / 60)}m ${Math.round(s % 60)}s` : `${Math.round(s)}s`)
