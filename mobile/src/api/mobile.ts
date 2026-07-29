import { apiFetch } from './client';

// ---------------------------------------------------------------------------
// /api/mobile/me/
// ---------------------------------------------------------------------------

export type PunchAction = 'CHECK_IN' | 'CHECK_OUT';

export interface ScheduleSlot {
  label: string;
  slot_type: 'shift' | 'rest';
  start_time: string | null; // "HH:MM"
  end_time: string | null; // "HH:MM"
}

export interface DaySchedule {
  is_rest_day: boolean;
  has_work_period: boolean;
  slots: ScheduleSlot[];
}

export interface PunchRecord {
  id: number;
  timestamp: string; // ISO datetime
  action: PunchAction;
  source: string;
  site_name: string | null;
}

export interface Site {
  id: number;
  name: string;
  latitude: number;
  longitude: number;
  radius_m: number;
}

export interface MeResponse {
  employee: {
    id: number;
    employee_no: string;
    name: string;
    tenant: { id: number; code: string; name: string };
  };
  date: string; // "YYYY-MM-DD"
  timezone: string;
  day_schedule: DaySchedule;
  punches_today: PunchRecord[];
  suggested_action: PunchAction;
  has_punched_in: boolean;
  sites: Site[];
}

export function getMe(): Promise<MeResponse> {
  return apiFetch<MeResponse>('/api/mobile/me/');
}

// ---------------------------------------------------------------------------
// /api/mobile/punch/
// ---------------------------------------------------------------------------

export interface PunchRequest {
  latitude: number;
  longitude: number;
  accuracy_m: number;
  action: PunchAction;
  idempotency_key: string;
  client_reported_at: string; // ISO datetime
  app_version?: string;
  mocked?: boolean;
}

export interface PunchResponse {
  status: 'ok';
  action: PunchAction;
  timestamp: string;
  site: { id: number; name: string };
  distance_m: number;
  zone: 'inside' | 'borderline';
  schedule: { in_schedule: boolean; delta_minutes: number | null };
}

/**
 * Error codes (carried on ApiError.code, extras on ApiError.payload):
 * 400 INVALID_COORDINATES | ACCURACY_TOO_LOW {max_accuracy_m}
 * 409 NO_SITE_CONFIGURED | SUGGESTED_ACTION_CHANGED {suggested_action}
 * 403 OUT_OF_ZONE {nearest_site:{id,name}, distance_m, tolerance_m} | PROFILE_NOT_LINKED
 * 429 TOO_SOON {retry_after_s}
 */
export function punch(request: PunchRequest): Promise<PunchResponse> {
  return apiFetch<PunchResponse>('/api/mobile/punch/', {
    method: 'POST',
    body: request,
  });
}

// ---------------------------------------------------------------------------
// /api/mobile/history/
// ---------------------------------------------------------------------------

export interface HistoryResponse {
  count: number;
  results: PunchRecord[];
}

export function getHistory(limit = 50): Promise<HistoryResponse> {
  return apiFetch<HistoryResponse>(`/api/mobile/history/?limit=${limit}`);
}

// ---------------------------------------------------------------------------
// /api/mobile/push-token/
// ---------------------------------------------------------------------------

export interface RegisterPushTokenRequest {
  token: string;
  platform: string;
  installation_id: string;
  app_version?: string;
  locale?: string;
  timezone?: string;
}

export function registerPushToken(
  request: RegisterPushTokenRequest
): Promise<void> {
  return apiFetch<void>('/api/mobile/push-token/', {
    method: 'POST',
    body: request,
  });
}

export function deletePushToken(token: string): Promise<void> {
  return apiFetch<void>('/api/mobile/push-token/', {
    method: 'DELETE',
    body: { token },
  });
}
