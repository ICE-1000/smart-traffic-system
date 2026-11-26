import { CameraOff, Maximize2, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { APPROACH_LABEL, CATEGORY_COLOUR, CATEGORY_LABEL } from '../lib/format'
import type { ApproachState, CameraInfo, VisionStats } from '../types/traffic'

/**
 * MJPEG stream served by the backend (cameras/receiver.py → /stream.mjpeg).
 * Boxes, track IDs and regions are drawn server-side on the same frame, so the
 * overlay can never drift out of sync with the video.
 */
export const cameraStreamUrl = (id: string, overlay = true, maxWidth = 640) =>
  `/api/cameras/${encodeURIComponent(id)}/stream.mjpeg?overlay=${overlay ? 1 : 0}&max_width=${maxWidth}`

const STATUS_TEXT: Record<CameraInfo['status'], string> = {
  online: 'ONLINE',
  connecting: 'CONNECTING',
  offline: 'OFFLINE',
  not_configured: 'NOT CONFIGURED',
  disabled: 'DISABLED',
}
const STATUS_CLASS: Record<CameraInfo['status'], string> = {
  online: 'bg-ok',
  connecting: 'bg-warn',
  offline: 'bg-crit',
  not_configured: 'bg-txt-mute',
  disabled: 'bg-txt-mute',
}
const AI_TEXT: Record<VisionStats['status'], string> = {
  starting: 'starting',
  loading_model: 'loading model',
  waiting_for_frames: 'waiting',
  detecting: 'detecting',
  disabled: 'off',
  model_error: 'model error',
  inference_error: 'error',
}

interface Props {
  camera?: CameraInfo
  approach: ApproachState | undefined
  title: string
  onClose?: () => void
  onMaximise?: () => void
  className?: string
  overlay?: boolean
  maxWidth?: number
}

/** Floating camera window, styled after the reference's video pop-ups. */
export function CameraPanel({ camera, approach, title, onClose, onMaximise, className = '', overlay = true, maxWidth = 640 }: Props) {
  const online = camera?.status === 'online'
  // Re-open the MJPEG connection whenever the camera comes back online.
  const [epoch, setEpoch] = useState(0)
  useEffect(() => {
    if (online) setEpoch((e) => e + 1)
  }, [online])
  const cat = approach?.congestion.category
  const source = approach?.measurement.source
  const v = camera?.vision
  return (
    <div className={`flex flex-col border border-[#2f7fe0] bg-ink-950/95 shadow-[0_0_14px_rgba(47,127,224,0.35)] ${className}`}>
      <div className="flex h-[26px] shrink-0 items-center justify-between bg-[#1a4f9c]/80 px-2 text-[12px] text-white">
        <span className="truncate">{title}</span>
        <div className="flex items-center gap-1.5">
          {onMaximise && (
            <button onClick={onMaximise} title="Open in Live Monitoring" className="text-txt-dim hover:text-white">
              <Maximize2 size={12} />
            </button>
          )}
          {onClose && (
            <button onClick={onClose} title="Hide window" className="text-[#ff6b6b] hover:text-white">
              <X size={14} />
            </button>
          )}
        </div>
      </div>
      <div className="relative aspect-video w-full overflow-hidden bg-black">
        {online && camera ? (
          <img key={epoch} src={`${cameraStreamUrl(camera.id, overlay, maxWidth)}&e=${epoch}`} alt={`${camera.name} live feed`} className="h-full w-full object-contain" />
        ) : (
          <div className="no-signal flex h-full w-full flex-col items-center justify-center gap-1.5 text-center">
            <CameraOff size={22} className="text-txt-mute" />
            <div className="num text-[13px] tracking-[0.2em] text-txt-dim">NO SIGNAL</div>
            <div className="max-w-[85%] text-[10px] leading-snug text-txt-mute">
              {camera ? `${camera.id} · ${camera.detail}` : 'No camera assigned to this approach'}
            </div>
          </div>
        )}
        <div className="absolute left-1.5 top-1.5 flex items-center gap-1 bg-ink-950/80 px-1.5 py-0.5 text-[10px] text-white">
          <span className={`h-1.5 w-1.5 rounded-full ${camera ? STATUS_CLASS[camera.status] : 'bg-txt-mute'}`} />
          {camera ? STATUS_TEXT[camera.status] : 'UNASSIGNED'}
          {online && camera && <span className="num text-txt-dim">· {camera.camera_fps.toFixed(0)} fps</span>}
        </div>
        {camera?.is_sample && (
          <div className="absolute bottom-1.5 left-1.5 border border-warn/70 bg-ink-950/85 px-1.5 py-0.5 text-[10px] font-semibold tracking-wider text-warn">
            SAMPLE FOOTAGE
          </div>
        )}
        <div className="absolute right-1.5 top-1.5 bg-ink-950/80 px-1.5 py-0.5 text-[10px] text-txt-dim" title={v?.model_error ?? undefined}>
          AI: {v ? AI_TEXT[v.status] : 'no input'}
          {v?.status === 'detecting' && <span className="num"> · {v.processing_fps.toFixed(1)} fps</span>}
        </div>
      </div>
      <div className="flex h-6 shrink-0 items-center justify-between gap-2 border-t border-line-soft px-2 text-[11px]">
        <span className="text-txt-dim">{approach ? `${APPROACH_LABEL[approach.approach]} approach` : '—'}</span>
        {approach && source === 'none' ? (
          <span className="text-[10px] font-semibold tracking-wider text-txt-mute">NO DATA</span>
        ) : (
          approach && (
            <span className="flex items-center gap-2">
              <span className="num text-white">
                {approach.measurement.vehicles_in_view} <span className="text-txt-dim">veh</span>
              </span>
              <span className="num" style={{ color: CATEGORY_COLOUR[cat!] }}>
                {CATEGORY_LABEL[cat!]}
              </span>
              <span className={`text-[9px] font-semibold ${source === 'vision' ? 'text-ok' : 'text-warn'}`} title={source === 'vision' ? 'Measured by the camera + AI' : 'Demo traffic model'}>
                {source === 'vision' ? 'AI' : 'SIM'}
              </span>
            </span>
          )
        )}
      </div>
    </div>
  )
}
