// Mirrors backend Pydantic schemas (app/schemas/event.py, app/schemas/ops.py).
// Hand-maintained rather than code-generated -- if these drift from the
// backend, that's a real bug to fix, not something a generator hides.

export type EventStatus =
  | "received"
  | "validated"
  | "queued"
  | "processing"
  | "delivered"
  | "failed"
  | "dead_lettered";

export type JobStatus =
  | "pending"
  | "queued"
  | "processing"
  | "delivered"
  | "failed"
  | "retrying"
  | "dead_lettered";

export type Channel = "email" | "sms" | "push";

export interface JobSummary {
  job_id: string;
  channel: Channel;
  status: JobStatus;
  attempt_count: number;
}

export interface EventResponse {
  event_id: string;
  event_type: string;
  status: EventStatus;
  created_at: string;
  jobs: JobSummary[];
}

export interface EventListItem {
  event_id: string;
  event_type: string;
  status: EventStatus;
  created_at: string;
}

export interface EventListResponse {
  items: EventListItem[];
  page: number;
  page_size: number;
  total: number;
}

export interface DeliveryAttempt {
  provider: string;
  provider_message_id: string | null;
  status: "attempted" | "delivered" | "failed";
  attempted_at: string;
  delivered_at: string | null;
  error_message: string | null;
}

export interface JobDetailResponse {
  job_id: string;
  event_id: string;
  channel: Channel;
  status: JobStatus;
  attempt_count: number;
  max_attempts: number;
  recipient: string;
  scheduled_at: string | null;
  claimed_at: string | null;
  lease_expires_at: string | null;
  created_at: string;
  updated_at: string;
  last_error: string | null;
  deliveries: DeliveryAttempt[];
}

export interface DeadLetterItem {
  id: string;
  original_job_id: string;
  event_id: string;
  channel: Channel;
  reason: string;
  attempt_count: number;
  failed_at: string;
  resolved_at: string | null;
}

export interface DeadLetterListResponse {
  items: DeadLetterItem[];
  page: number;
  page_size: number;
  total: number;
}

export interface DeadLetterRetryResponse {
  job_id: string;
  event_id: string;
  channel: Channel;
  status: string;
}

export interface OpsOverviewResponse {
  events_by_status: Record<string, number>;
  jobs_by_channel_and_status: Record<Channel, Record<JobStatus, number>>;
  dead_letter_count: number;
  rate_limit_denied_total: number;
  rate_limit_denied_by_channel: Record<Channel, number>;
  configured_rate_limits_per_minute: Record<Channel, number>;
  in_process_counters_note: string;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
  };
}
