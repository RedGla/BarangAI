export type Category =
  | 'flooding'
  | 'fallen_trees'
  | 'broken_streetlights'
  | 'exposed_wiring'
  | 'potholes'
  | 'uncollected_garbage'
  | 'damaged_signage'
  | 'other'
export type Hazard = 'electrical_hazard' | 'blocks_road' | 'risk_to_people'
export type Status = 'Pending' | 'Under Verification' | 'Accepted' | 'In Progress' | 'Resolved' | 'Rejected'
export type ReportEvent = { id?: string; to_status?: Status; created_at?: string; note?: string }
export type StaffAction = { id: string; kind: 'action' | 'coordination'; note: string; created_at: string }
export type Duplicate = {
  id: string
  candidate_report_id: string
  score: number
  decision: 'pending' | 'confirmed' | 'rejected'
}
export type DuplicateResult = {
  embedding_available: boolean
  suggestions: Duplicate[]
  manual_review_required: boolean
}
export type Report = {
  id: string
  status: Status
  resident_category: Category
  model_category?: Category | null
  verified_category?: Category | null
  description?: string | null
  latitude?: number
  longitude?: number
  location_label?: string | null
  hazards?: Hazard[]
  case_id?: string | null
  case_confirmed?: boolean
  /** Staff only; null once closed. */
  priority?: Priority | null
  created_at?: string
  events?: ReportEvent[]
  actions?: StaffAction[]
}
export type Prediction = {
  prediction_available: boolean
  model_category: Category | null
  confidence: number | null
  suggested_description?: string | null
  // 'agreed' (both models), 'vision' (Cloudflare only), 'checker' (MobileCLIP only)
  category_source?: 'agreed' | 'vision' | 'checker' | null
  needs_check?: boolean
  // false when the vision model looked and saw nothing wrong
  problem_seen?: boolean
  hazards?: Hazard[]
}
export type PriorityReason =
  | { code: 'category'; detail: Category; points: number }
  | { code: 'hazard'; detail: Hazard; points: number }
  | { code: 'residents'; detail: number; points: number }
  | { code: 'recent'; detail: number; points: number }
/** A suggestion for staff from severity, recency and independent residents; it never reorders anything itself. */
export type Priority = { level: 'high' | 'medium' | 'low'; score: number; reasons: PriorityReason[] }
export type CaseMember = {
  id: string
  status: Status
  resident_category: Category
  created_at: string
  confirmed: boolean
}
/** A grouped case as one report sees it; staff also get its reports. */
export type ReportCase = {
  id: string
  category: Category
  location_label?: string | null
  status: Status | null
  confirmed: boolean
  /** Hidden from residents until staff accept the case. */
  reports: number | null
  contributors: number | null
  members?: CaseMember[]
}
/** An accepted case on the residents' shared map: no photos, descriptions or names. */
export type CommunityCase = {
  id: string
  category: Category
  status: Status
  latitude: number
  longitude: number
  location_label?: string | null
  /** Days only (YYYY-MM-DD, Philippine time). */
  first_reported_on: string
  last_reported_on: string
  contributors: number
  hazards: Hazard[]
  open_for_evidence: boolean
  contributed: boolean
}
