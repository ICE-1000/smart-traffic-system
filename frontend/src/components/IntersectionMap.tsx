import { memo } from 'react'
import { APPROACH_LABEL, CATEGORY_COLOUR, SIGNAL_COLOUR } from '../lib/format'
import type { Approach, Snapshot } from '../types/traffic'
import { APPROACHES } from '../types/traffic'

/**
 * Custom four-way intersection drawn in SVG, centred on (0,0).
 * Geometry is defined once for the NORTH arm and rotated for the others.
 * Zambia drives on the LEFT, so inbound lanes sit on the driver's left:
 * the north arm's inbound lanes are on the east half of the road.
 *
 * Queued vehicles are drawn from the measured queue COUNT per approach
 * (positions are schematic, not tracked positions).
 */
export const ROAD_HALF = 70 // road half-width in map units
const LANE = 22
const MEDIAN = 4
const STOP_Y = -(ROAD_HALF + 26)
const ROT: Record<Approach, number> = { north: 0, east: 90, south: 180, west: 270 }
const CAM_STATUS_COLOUR: Record<string, string> = {
  online: '#2ed47a',
  connecting: '#ffb020',
  offline: '#ff4d4f',
  not_configured: '#5f7aa3',
  disabled: '#5f7aa3',
}

const BLOCKS = (() => {
  // Deterministic city blocks for the background; skip the two main roads.
  const out: { x: number; y: number; w: number; h: number }[] = []
  const step = 150
  for (let gx = -12; gx < 12; gx++)
    for (let gy = -9; gy < 9; gy++) {
      const x = gx * step + 14
      const y = gy * step + 14
      const w = step - 28 - ((gx * 7 + gy * 3) % 3 === 0 ? 30 : 0)
      const h = step - 28 - ((gx * 5 + gy * 11) % 4 === 0 ? 34 : 0)
      const hitsNS = x < ROAD_HALF + 20 && x + w > -ROAD_HALF - 20
      const hitsEW = y < ROAD_HALF + 20 && y + h > -ROAD_HALF - 20
      if (!hitsNS && !hitsEW) out.push({ x, y, w, h })
    }
  return out
})()

function Arm({ approach, snap, showQueues }: { approach: Approach; snap: Snapshot | null; showQueues: boolean }) {
  const st = snap?.approaches[approach]
  const colour = st?.signal ?? 'red'
  const queue = st?.measurement.queue_count ?? 0
  const cat = st?.congestion.category ?? 'free'
  const lanes = [0, 1, 2]
  const maxRows = 26
  const shown = Math.min(queue, maxRows * 3)
  const inboundX = (i: number) => MEDIAN + LANE * i

  return (
    <g transform={`rotate(${ROT[approach]})`}>
      {/* active approach highlight */}
      {colour !== 'red' && (
        <rect x={MEDIAN} y={-900} width={ROAD_HALF - MEDIAN} height={900 + STOP_Y} fill={SIGNAL_COLOUR[colour]} opacity={0.09} />
      )}
      {/* lane lines */}
      {[LANE + MEDIAN, 2 * LANE + MEDIAN].flatMap((x) => [x, -x]).map((x) => (
        <line key={x} x1={x} x2={x} y1={-900} y2={STOP_Y - 4} stroke="#c8d3e6" strokeOpacity={0.45} strokeWidth={1.2} strokeDasharray="10 12" />
      ))}
      {/* median */}
      <line x1={-1.6} x2={-1.6} y1={-900} y2={STOP_Y} stroke="#e8b93a" strokeOpacity={0.8} strokeWidth={1.2} />
      <line x1={1.6} x2={1.6} y1={-900} y2={STOP_Y} stroke="#e8b93a" strokeOpacity={0.8} strokeWidth={1.2} />
      {/* crosswalk */}
      {Array.from({ length: 14 }, (_, i) => (
        <rect key={i} x={-ROAD_HALF + 4 + i * 10} y={-ROAD_HALF - 20} width={5} height={16} fill="#d7e0ef" opacity={0.55} />
      ))}
      {/* stop line coloured by simulated signal */}
      <rect x={MEDIAN} y={STOP_Y - 2} width={ROAD_HALF - MEDIAN} height={4} fill={SIGNAL_COLOUR[colour]} />
      {/* lane arrows (left, straight, right — LHT) */}
      {lanes.map((i) => {
        const cx = inboundX(i) + LANE / 2
        const y = STOP_Y - 34
        const d =
          i === 0
            ? `M${cx + 2} ${y - 14} L${cx + 2} ${y} L${cx + 7} ${y}` // left turn (screen-right when southbound)
            : i === 1
              ? `M${cx} ${y - 16} L${cx} ${y + 2}`
              : `M${cx - 2} ${y - 14} L${cx - 2} ${y} L${cx - 7} ${y}`
        return <path key={i} d={d} stroke="#c8d3e6" strokeOpacity={0.5} strokeWidth={2} fill="none" />
      })}
      {/* queued vehicles (count-based) */}
      {showQueues &&
        Array.from({ length: shown }, (_, k) => {
          const lane = k % 3
          const row = Math.floor(k / 3)
          return (
            <rect
              key={k}
              x={inboundX(lane) + 5}
              y={STOP_Y - 8 - 20 - row * 25}
              width={LANE - 10}
              height={20}
              rx={3}
              fill={CATEGORY_COLOUR[cat]}
              opacity={0.92}
              stroke="#050d1f"
              strokeWidth={1}
            />
          )
        })}
      {/* signal head on the kerb */}
      <g transform={`translate(${ROAD_HALF + 8} ${STOP_Y - 12})`}>
        <rect x={0} y={-24} width={14} height={40} rx={3} fill="#0b0f17" stroke="#2a3a55" />
        {(['red', 'yellow', 'green'] as const).map((l, i) => (
          <circle key={l} cx={7} cy={-16 + i * 12} r={4.2} fill={l === colour ? SIGNAL_COLOUR[l] : '#1d2533'} style={l === colour ? { filter: `drop-shadow(0 0 4px ${SIGNAL_COLOUR[l]})` } : undefined} />
        ))}
      </g>
    </g>
  )
}

interface Props {
  snapshot: Snapshot | null
  showQueues: boolean
  scale: number
  /** junction centre in px within the SVG */
  cx: number
  cy: number
  /** distance in map units from the junction centre to the visible edge (vertical, horizontal); chips sit just inside it */
  extent?: { v: number; h: number }
}

export const IntersectionMap = memo(function IntersectionMap({ snapshot, showQueues, scale, cx, cy, extent = { v: 300, h: 300 } }: Props) {
  const cams = new Map(snapshot?.cameras.map((c) => [c.approach, c]) ?? [])
  return (
    <svg className="absolute inset-0 h-full w-full" aria-label="Intersection schematic">
      <g transform={`translate(${cx} ${cy}) scale(${scale})`}>
        <rect x={-3000} y={-2000} width={6000} height={4000} fill="#10264d" />
        {BLOCKS.map((b, i) => (
          <rect key={i} x={b.x} y={b.y} width={b.w} height={b.h} fill="#0b1c3d" stroke="#16326a" strokeWidth={1} />
        ))}
        {/* main roads */}
        <rect x={-ROAD_HALF} y={-1500} width={ROAD_HALF * 2} height={3000} fill="#1b2638" />
        <rect x={-2000} y={-ROAD_HALF} width={4000} height={ROAD_HALF * 2} fill="#1b2638" />
        <rect x={-ROAD_HALF - 3} y={-1500} width={3} height={3000} fill="#2b3a55" />
        <rect x={ROAD_HALF} y={-1500} width={3} height={3000} fill="#2b3a55" />
        <rect x={-2000} y={-ROAD_HALF - 3} width={4000} height={3} fill="#2b3a55" />
        <rect x={-2000} y={ROAD_HALF} width={4000} height={3} fill="#2b3a55" />
        {APPROACHES.map((a) => (
          <Arm key={a} approach={a} snap={snapshot} showQueues={showQueues} />
        ))}
        {/* intersection box */}
        <rect x={-ROAD_HALF} y={-ROAD_HALF} width={ROAD_HALF * 2} height={ROAD_HALF * 2} fill="#1f2b40" />
        <rect x={-ROAD_HALF + 10} y={-ROAD_HALF + 10} width={ROAD_HALF * 2 - 20} height={ROAD_HALF * 2 - 20} fill="none" stroke="#e8b93a" strokeOpacity={0.25} strokeDasharray="6 8" />
        {APPROACHES.map((a) => {
          // Label chip sits on the road itself, beyond the queue area, so camera windows never hide it.
          // keep the whole chip inside the visible area (chips are drawn at 1/scale so they stay legible)
          const k = 1 / Math.max(scale, 0.75)
          const v = Math.max(ROAD_HALF + 40, extent.v - 22 * k - 8)
          const h = Math.max(ROAD_HALF + 80, extent.h - 66 * k - 8)
          const [x, y] = { north: [0, -v], south: [0, v], east: [h, 0], west: [-h, 0] }[a]
          const st = snapshot?.approaches[a]
          const cam = cams.get(a)
          return (
            <g key={a} transform={`translate(${x} ${y}) scale(${1 / Math.max(scale, 0.75)})`}>
              <rect x={-66} y={-22} width={132} height={44} rx={3} fill="#071330" fillOpacity={0.92} stroke={st?.signal === 'green' ? '#2ed47a' : '#2f7fe0'} />
              <circle cx={-54} cy={-8} r={5} fill={cam ? (CAM_STATUS_COLOUR[cam.status] ?? '#5f7aa3') : '#5f7aa3'}>
                <title>{cam ? `${cam.id}: ${cam.status}` : 'No camera'}</title>
              </circle>
              <text x={-44} y={-3} className="fill-white font-din" fontSize={14} fontWeight={600} letterSpacing={1}>
                {APPROACH_LABEL[a].toUpperCase()}
              </text>
              {st && st.measurement.source === 'none' && (
                <text x={-58} y={15} className="font-din" fontSize={11} fill="#8fa6c9">
                  no data · fallback
                </text>
              )}
              {st && st.measurement.source !== 'none' && (
                <text x={-58} y={15} className="font-din" fontSize={11} fill={CATEGORY_COLOUR[st.congestion.category]}>
                  {st.measurement.queue_count} queued · {st.congestion.score.toFixed(0)}
                  <tspan fill={st.measurement.source === 'vision' ? '#2ed47a' : '#ffb020'}>{st.measurement.source === 'vision' ? ' · AI' : ' · SIM'}</tspan>
                  <title>{`Queued vehicles · congestion score · ${st.measurement.source === 'vision' ? 'camera + AI measurement' : 'demo model'}`}</title>
                </text>
              )}
            </g>
          )
        })}
      </g>
    </svg>
  )
})
