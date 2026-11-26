import type { SignalColour } from '../types/traffic'
import { SIGNAL_COLOUR } from '../lib/format'

/** HTML traffic-light head (used in tables and cards). */
export function SignalHead({ colour, size = 10, horizontal = false }: { colour: SignalColour; size?: number; horizontal?: boolean }) {
  const lamps: SignalColour[] = ['red', 'yellow', 'green']
  return (
    <span
      className={`inline-flex gap-[3px] rounded-[3px] border border-[#2a3a55] bg-[#0b0f17] p-[3px] ${horizontal ? 'flex-row' : 'flex-col'}`}
      aria-label={`Signal ${colour}`}
    >
      {lamps.map((l) => (
        <span
          key={l}
          className="rounded-full"
          style={{
            width: size,
            height: size,
            background: l === colour ? SIGNAL_COLOUR[l] : '#1d2533',
            boxShadow: l === colour ? `0 0 ${size}px ${SIGNAL_COLOUR[l]}` : undefined,
          }}
        />
      ))}
    </span>
  )
}
