// Mirrors the backend snapshot contract (backend/app/services/runtime.py).

export type Approach = 'north' | 'south' | 'east' | 'west'
export const APPROACHES: Approach[] = ['north', 'south', 'east', 'west']
export type SignalColour = 'red' | 'yellow' | 'green'
export type CongestionCategory = 'free' | 'light' | 'moderate' | 'heavy' | 'critical'
export type DataSource = 'demo' | 'vision' | 'none' | 'model'
export type SnapshotSource = DataSource | 'mixed'
export type DataSourceMode = 'auto' | 'vision' | 'demo'
export type CameraStatusName = 'not_configured' | 'disabled' | 'offline' | 'connecting' | 'online'

export interface Measurement {
  approach: Approach
  queue_count: number
  queue_length_m: number
  avg_wait_s: number
  max_wait_s: number
  arrival_rate_vpm: number
  departure_rate_vpm: number
  moving_ratio: number
  vehicles_in_view: number
  heavy_vehicles: number
  light_vehicles: number
  pedestrian_request: boolean
  source: DataSource
  pedestrians_in_view: number
}

export interface Congestion {
  approach: Approach
  score: number
  category: CongestionCategory
  components: Record<string, number>
  contributions: Record<string, number>
}

export interface ApproachIndices {
  samples: number
  mean_delay_s: number | null
  ci: number | null
  tti: number | null
  section_m: number
  free_flow_s: number | null
}

export interface ApproachState {
  approach: Approach
  camera_id: string | null
  measurement: Measurement
  congestion: Congestion
  signal: SignalColour
  time_since_served_s: number
  indices: ApproachIndices
}

export interface RankingRow {
  approach: Approach
  priority_index: number
  congestion_score: number
  queue_count: number
  avg_wait_s: number
  time_since_served_s: number
  eligible: boolean
  note: string
}

export interface PriorityState {
  recommended: Approach | null
  next_recommended: Approach | null
  rule: 'demand' | 'starvation' | 'max_skip' | 'no_data' | 'no_demand'
  reason: string
  ranking: RankingRow[]
  current_green: Approach
  stage: 'green' | 'yellow' | 'all_red'
}

export interface SignalEvent {
  ts: number
  kind: string
  approach: Approach | null
  reason: string
}

export interface SignalState {
  current: Approach
  stage: 'green' | 'yellow' | 'all_red'
  stage_elapsed_s: number
  target: Approach | null
  remaining_min_green_s: number
  remaining_max_green_s: number
  colours: Record<Approach, SignalColour>
  time_since_served_s: Record<Approach, number>
  served_seconds: Record<Approach, number>
  config: { min_green_s: number; max_green_s: number; yellow_s: number; clearance_s: number; preempt_min_green_s: number }
  events: SignalEvent[]
  preemption: { approach: Approach; hold_s: number; reason: string; active_since: number | null; requested_at: number } | null
}

export type NodeType = 'signalised' | 'roundabout' | 'unconfirmed'
export interface Site {
  id: string
  name: string
  node_type: NodeType
  corridor: string | null
  description: string | null
  city?: string
  active?: boolean
}

export interface Incident {
  key: string
  kind: 'blocked_discharge' | 'stalled_vehicle' | 'spillback' | 'camera_failure'
  approach: Approach | null
  severity: 'warning' | 'critical'
  started: number
  message: string
  ended: number | null
  db_id: number | null
  acknowledged: boolean
}

export interface EvaluationSide {
  mean_delay_s: number
  vehicle_hours_delay: number
  throughput_vph: number
  queued_now: number
  departed: number
  stop_rate: number
}
export interface EvaluationBrief {
  elapsed_s: number
  warming_up: boolean
  run_started: number
  adaptive: EvaluationSide
  fixed: EvaluationSide
  improvement_pct: Record<'mean_delay' | 'vehicle_hours_delay' | 'stop_rate' | 'throughput', number | null>
}

export interface VisionStats {
  status: 'starting' | 'loading_model' | 'waiting_for_frames' | 'detecting' | 'disabled' | 'model_error' | 'inference_error'
  processing_fps: number
  detection_ms: number
  class_counts: Record<string, number>
  state_counts: Record<string, number>
  active_tracks: number
  model_error: string | null
}

export interface CameraInfo {
  id: string
  name: string
  approach: Approach
  stream_url: string
  has_stream_url: boolean
  is_sample: boolean
  has_regions: boolean
  enabled: boolean
  processing_width: number
  processing_fps: number
  status: CameraStatusName
  detail: string
  last_seen: number | null
  camera_fps: number
  resolution: [number, number] | null
  reconnects: number
  vision: VisionStats | null
}

export interface SeriesPoint {
  ts: number
  arrivals: number
  departures: number
  in_view: number
  avg_wait: number
  [key: string]: number
}

export interface SystemStatus {
  backend: string
  database: string
  websocket_clients: number
  ai_model: string
  ai_model_name: string
  ai_model_error: string | null
  ai_hint: string | null
  ai_tracker: string | null
  video_processing: string
  data_source: SnapshotSource
  data_source_mode: DataSourceMode
  system_memory_percent: number
  cpu_percent: number
  system_cpu_percent: number
  memory_mb: number
  tick_ms: number
  processing_fps: number | null
  detection_ms: number | null
  active_feeds: number
  uptime_s: number
}

export interface Snapshot {
  ts: number
  source: SnapshotSource
  data_source_mode: DataSourceMode
  intersection: { id: string; name: string }
  site: Site
  incidents: Incident[]
  evaluation: EvaluationBrief
  approaches: Record<Approach, ApproachState>
  priority: PriorityState
  signal: SignalState
  totals: {
    vehicles_detected: number
    vehicles_in_view: number
    heavy_in_view: number
    light_in_view: number
    queued: number
    avg_wait_s: number
    most_congested: { approach: Approach; score: number; category: CongestionCategory }
    cameras_online: number
    cameras_total: number
    critical_approaches: number
    spillback_approaches: number
    no_data_approaches: number
  }
  cameras: CameraInfo[]
  point: SeriesPoint
  demo: { rates_vpm: Record<Approach, number> } | null
  system: SystemStatus
}
