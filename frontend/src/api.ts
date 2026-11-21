import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message) }
}

export async function api<T>(path: string, method = 'GET', data?: unknown): Promise<T> {
  const headers: Record<string, string> = { 'X-MeetFlow-Client': '1' }
  const csrf = document.cookie.split('; ').find(value => value.startsWith('meetflow_csrf='))?.split('=')[1]
  if (csrf) headers['X-CSRF-Token'] = csrf
  const body = data instanceof FormData ? data : data === undefined ? undefined : JSON.stringify(data)
  if (body && !(body instanceof FormData)) headers['Content-Type'] = 'application/json'
  const response = await fetch('/api' + path, { method, headers, body, credentials: 'same-origin' })
  if (!response.ok) {
    const result = await response.json().catch(() => ({}))
    throw new ApiError(result.message ?? 'The request failed. Please try again.', response.status)
  }
  return response.json()
}

export function useData<T>(path: string, enabled = true) {
  return useQuery({ queryKey: [path], queryFn: () => api<T>(path), enabled, retry: false })
}

export function useAction() {
  const cache = useQueryClient()
  return useMutation({
    mutationFn: ({ path, method = 'POST', data }: { path: string; method?: string; data?: unknown }) =>
      api<Record<string, unknown>>(path, method, data),
    onSuccess: () => cache.invalidateQueries(),
  })
}

export type Mode = 'live' | 'demo'
export type Account = { display_name: string; email: string; ai_mode: Mode; ai_ready: boolean }
export type MeetingRef = { id: string; title: string; meeting_date: string }
export type Meeting = MeetingRef & {
  processing_mode: Mode; status: string; failure_reason: string | null; source_format: string
}
export type Decision = {
  id: string; meeting_id: string; subject_key: string; topic: string; description: string;
  responsible_speaker: string | null; evidence_excerpt: string; evidence_ts: string | null;
  evidence_verified: boolean; status: string; processing_mode: Mode; updated_at: string; created_at: string;
  superseded_by_decision_id: string | null
}
export type Task = {
  id: string; meeting_id: string; title: string; description: string; owner: string | null;
  deadline: string | null; deadline_raw: string | null; no_deadline_confirmed: boolean; evidence_excerpt: string; evidence_ts: string | null;
  evidence_verified: boolean; approval_status: string; github_state: string; github_issue_url: string | null;
  github_error: string | null; completed_at: string | null; processing_mode: Mode
}
export type Segment = { id: string; speaker_label: string | null; start_ts: string | null; text: string }
export type Detail = Meeting & { segments: Segment[]; decisions: Decision[]; action_items: Task[]; participants: { name: string }[] }
export type Relation = {
  id: string; relation: string; resolution: string; reason: string; new_evidence: string; prior_evidence: string;
  processing_mode: Mode; new: { decision: Decision; meeting: MeetingRef }; prior: { decision: Decision; meeting: MeetingRef }
}
export type Notice = { id: string; kind: string; message: string; read_at: string | null; processing_mode: Mode }
export type Digest = {
  id: string; person_name: string; week_start: string; processing_mode: Mode;
  payload: { tasks: { id: string; title: string; deadline: string | null; status: string }[]; decisions: string[]; conflicts: string[] }
}
export type Settings = { github_repo: string | null; timezone: string; github_ready: boolean }

