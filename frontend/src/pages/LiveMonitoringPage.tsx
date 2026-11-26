import { CameraPanel } from '../components/CameraPanel'
import { SimBadge, Waiting } from '../components/Panel'
import { SignalHead } from '../components/SignalHead'
import { CategoryTag, PageGrid } from '../components/ui'
import { useLiveData } from '../hooks/useLiveData'
import { APPROACH_LABEL, secs } from '../lib/format'
import { APPROACHES } from '../types/traffic'

/** 2×2 camera wall with per-approach readouts. */
export function LiveMonitoringPage() {
  const { snapshot } = useLiveData()
  if (!snapshot) return <Waiting />
  const cams = new Map(snapshot.cameras.map((c) => [c.approach, c]))
  return (
    <PageGrid>
      <div className="mb-2 flex items-center gap-2 text-[12px] text-txt-dim">
        Live camera wall · {snapshot.cameras.filter((c) => c.status === 'online').length}/{snapshot.cameras.length} feeds online
        <SimBadge />
      </div>
      <div className="grid gap-3 xl:grid-cols-2">
        {APPROACHES.map((a) => {
          const st = snapshot.approaches[a]
          const m = st.measurement
          const cam = cams.get(a)
          return (
            <div key={a} className="flex flex-col">
              <CameraPanel camera={cams.get(a)} approach={st} title={`${cams.get(a)?.id ?? '—'} · ${cams.get(a)?.name ?? `${APPROACH_LABEL[a]} approach`}`} maxWidth={960} />
              <div className="grid grid-cols-6 items-center gap-2 border border-t-0 border-line-soft bg-ink-900/90 px-3 py-2 text-[11px]">
                {m.source === 'none' && <div className="col-span-6 text-txt-mute">No measurement — camera or AI not delivering data. Priority falls back to fixed-time service for this approach.</div>}
                <Readout k="Queued" v={m.queue_count} />
                <Readout k="Queue" v={`${Math.round(m.queue_length_m)} m`} />
                <Readout k="Avg wait" v={secs(m.avg_wait_s)} />
                <Readout k="Score" v={st.congestion.score.toFixed(0)} />
                <div>
                  <CategoryTag category={st.congestion.category} />
                </div>
                <div className="flex justify-end">
                  <SignalHead colour={st.signal} size={8} horizontal />
                </div>
                {cam?.vision && cam.vision.status === 'detecting' && (
                  <div className="num col-span-6 flex flex-wrap gap-x-4 gap-y-1 border-t border-line-soft/60 pt-1.5 text-[10px] text-txt-dim">
                    <span>Detected now: {Object.entries(cam.vision.class_counts).map(([k, n]) => `${k} ${n}`).join(' · ') || 'nothing'}</span>
                    <span>Tracks {cam.vision.active_tracks}</span>
                    <span>{cam.vision.processing_fps.toFixed(1)} fps · {cam.vision.detection_ms.toFixed(0)} ms/frame</span>
                    <span className="text-txt-mute">Boxes: amber queued · blue approaching · green departed · white pedestrian</span>
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </PageGrid>
  )
}

function Readout({ k, v }: { k: string; v: string | number }) {
  return (
    <div>
      <div className="text-txt-dim">{k}</div>
      <div className="num text-[15px] text-num">{v}</div>
    </div>
  )
}
