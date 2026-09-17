/**
 * Shared API client for CohortOS.
 * One place for base URL, token refresh, 429 / offline handling.
 * Used identically in Electron (localhost) and web builds.
 * Per UI_BUILD_PLAN §0 / Portion 11 — no business logic here.
 */

export type SyncState = "offline" | "syncing" | "synced" | "conflict";

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
  account_id?: string;
  tenant_id?: string;
  family_id?: string;
}

export interface ApiError {
  status: number;
  detail: string;
  retryAfter?: number;
}

type RequestOptions = {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
  skipAuth?: boolean;
  signal?: AbortSignal;
};

const STORAGE_KEYS = {
  // access token is MEMORY-ONLY (short-lived). Refresh persists for stay-signed-in.
  tenant: "cohortos_tenant_id",
  account: "cohortos_account_id",
  refresh: "cohortos_refresh_token",
} as const;

/** In-memory short-lived access token (web + Electron). */
let memoryAccessToken: string | undefined;
let memoryAccountId: string | undefined;
let memoryTenantId: string | undefined;

/** Electron safeStorage for refresh token when running under Electron. */
function isElectron(): boolean {
  return typeof window !== "undefined" && !!(window as any).electronAPI?.safeStorage;
}

async function electronStoreRefresh(token: string) {
  try {
    await (window as any).electronAPI.safeStorage.set("cohortos_refresh", token);
  } catch { /* ignore */ }
}

async function electronLoadRefresh(): Promise<string | undefined> {
  try {
    return await (window as any).electronAPI.safeStorage.get("cohortos_refresh");
  } catch {
    return undefined;
  }
}

async function electronClearRefresh() {
  try {
    await (window as any).electronAPI.safeStorage.remove("cohortos_refresh");
  } catch { /* ignore */ }
}

let baseUrl = (typeof window !== "undefined" && (window as any).__COHORTOS_API_BASE__) ||
  import.meta.env.VITE_API_BASE ||
  "http://127.0.0.1:8741";

let onSyncStateChange: ((state: SyncState) => void) | null = null;
let currentSyncState: SyncState = "offline";
let lastSyncedAt: number | null = null;
let refreshPromise: Promise<AuthTokens | null> | null = null;

export function setApiBaseUrl(url: string) {
  baseUrl = url.replace(/\/$/, "");
}

export function getApiBaseUrl() {
  return baseUrl;
}

export function setSyncStateListener(fn: (state: SyncState) => void) {
  onSyncStateChange = fn;
  fn(currentSyncState);
}

export function setSyncState(state: SyncState) {
  currentSyncState = state;
  if (state === "synced") lastSyncedAt = Date.now();
  onSyncStateChange?.(state);
}

export function getSyncState(): SyncState {
  return currentSyncState;
}

export function getLastSyncedAt(): number | null {
  return lastSyncedAt;
}

export function loadTokens(): Partial<AuthTokens> {
  return {
    access_token: memoryAccessToken,
    tenant_id: memoryTenantId || (typeof localStorage !== "undefined" ? localStorage.getItem(STORAGE_KEYS.tenant) || undefined : undefined),
    account_id: memoryAccountId || (typeof localStorage !== "undefined" ? localStorage.getItem(STORAGE_KEYS.account) || undefined : undefined),
  };
}

export function saveTokens(tokens: Partial<AuthTokens>) {
  if (tokens.access_token) memoryAccessToken = tokens.access_token;
  if (tokens.account_id) {
    memoryAccountId = tokens.account_id;
    if (typeof localStorage !== "undefined") localStorage.setItem(STORAGE_KEYS.account, tokens.account_id);
  }
  if (tokens.tenant_id) {
    memoryTenantId = tokens.tenant_id;
    if (typeof localStorage !== "undefined") localStorage.setItem(STORAGE_KEYS.tenant, tokens.tenant_id);
  }
  // Persist refresh for stay-signed-in across app/OS restart (30-day server TTL).
  if (tokens.refresh_token) {
    if (typeof localStorage !== "undefined") {
      localStorage.setItem(STORAGE_KEYS.refresh, tokens.refresh_token);
    }
    if (isElectron()) {
      void electronStoreRefresh(tokens.refresh_token);
    }
  }
}

export function clearTokens() {
  memoryAccessToken = undefined;
  memoryAccountId = undefined;
  memoryTenantId = undefined;
  if (typeof localStorage !== "undefined") {
    localStorage.removeItem(STORAGE_KEYS.tenant);
    localStorage.removeItem(STORAGE_KEYS.account);
    // legacy cleanup
    localStorage.removeItem("cohortos_access_token");
    localStorage.removeItem(STORAGE_KEYS.refresh);
  }
  if (isElectron()) void electronClearRefresh();
}

async function refreshAccessToken(): Promise<AuthTokens | null> {
  // Prefer body refresh_token (Electron safeStorage or localStorage) so file:// and
  // laptop reboot still restore session. Cookie also sent when same-site web.
  let body: Record<string, string> | undefined;
  let rt: string | undefined;
  if (isElectron()) {
    rt = await electronLoadRefresh();
  }
  if (!rt && typeof localStorage !== "undefined") {
    rt = localStorage.getItem(STORAGE_KEYS.refresh) || undefined;
  }
  if (rt) {
    body = { refresh_token: rt };
  } else if (isElectron()) {
    // Electron without stored refresh cannot rely on cross-origin cookie from API
    return null;
  }

  try {
    const res = await fetch(`${baseUrl}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: body ? JSON.stringify(body) : JSON.stringify({}),
    });
    if (!res.ok) {
      // Only end session on definitive auth rejection — not 5xx / 429.
      if (res.status === 401 || res.status === 403) {
        clearTokens();
      }
      return null;
    }
    const data = (await res.json()) as AuthTokens;
    saveTokens(data);
    return data;
  } catch {
    // Network failure — keep existing access if any; offline is normal
    return memoryAccessToken ? { access_token: memoryAccessToken, refresh_token: "", token_type: "bearer" } : null;
  }
}

async function ensureAccessToken(): Promise<string | null> {
  const { access_token } = loadTokens();
  if (access_token) return access_token;

  if (!refreshPromise) {
    refreshPromise = refreshAccessToken().finally(() => {
      refreshPromise = null;
    });
  }
  const tokens = await refreshPromise;
  return tokens?.access_token ?? null;
}

export async function apiRequest<T = unknown>(
  path: string,
  options: RequestOptions = {}
): Promise<T> {
  const { method = "GET", body, headers = {}, skipAuth = false, signal } = options;
  const url = path.startsWith("http") ? path : `${baseUrl}${path.startsWith("/") ? "" : "/"}${path}`;

  const finalHeaders: Record<string, string> = {
    "Content-Type": "application/json",
    ...headers,
  };

  if (!skipAuth) {
    const token = await ensureAccessToken();
    if (token) finalHeaders["Authorization"] = `Bearer ${token}`;
  }

  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers: finalHeaders,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal,
      credentials: "include",
    });
  } catch (err) {
    // Network error → offline
    setSyncState("offline");
    const error: ApiError = {
      status: 0,
      detail: "Network unavailable — working offline",
    };
    throw error;
  }

  // 429 rate limit (SPEC §9.3 pattern)
  if (response.status === 429) {
    const retryAfter = parseInt(response.headers.get("Retry-After") || "60", 10);
    const detail = (await response.json().catch(() => ({})))?.detail || "Rate limit exceeded";
    const error: ApiError = { status: 429, detail, retryAfter };
    throw error;
  }

  // 401 → try one refresh then retry once
  if (response.status === 401 && !skipAuth) {
    const refreshed = await refreshAccessToken();
    if (refreshed?.access_token) {
      finalHeaders["Authorization"] = `Bearer ${refreshed.access_token}`;
      response = await fetch(url, {
        method,
        headers: finalHeaders,
        body: body !== undefined ? JSON.stringify(body) : undefined,
        signal,
      });
    }
  }

  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const error: ApiError = {
      status: response.status,
      detail: payload.detail || response.statusText || "Request failed",
    };
    throw error;
  }

  // Empty body (204 etc.)
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  if (!text) return undefined as T;
  return JSON.parse(text) as T;
}

// ── Auth endpoints (existing backend) ────────────────────────────────

export type CentreChoice = {
  tenant_id: string;
  centre_name: string;
  role?: string;
};

export async function startCentreTrial(params: {
  centre_name: string;
  owner_phone: string;
  owner_name?: string;
  owner_email?: string;
  student_count?: number;
}) {
  return apiRequest<{
    tenant_id: string;
    centre_name: string;
    centre_code: string;
    trial_ends_at: string;
    account_id: string;
    message: string;
  }>("/auth/centre-trial", {
    method: "POST",
    body: params,
    skipAuth: true,
  });
}

export async function requestOtp(params: {
  phone?: string;
  email?: string;
  tenant_id?: string;
}) {
  return apiRequest<{
    otp_id: string | null;
    message?: string;
    tenant_id?: string;
    centres?: CentreChoice[];
    _test_code?: string;
  }>("/auth/request-otp", {
    method: "POST",
    body: params,
    skipAuth: true,
  });
}

export async function verifyOtp(params: {
  otp_id: string;
  code: string;
  tenant_id?: string;
}) {
  const tokens = await apiRequest<AuthTokens>("/auth/verify-otp", {
    method: "POST",
    body: params,
    skipAuth: true,
  });
  saveTokens(tokens);
  return tokens;
}

export async function createBatch(tenantId: string, body: {
  days: string[];
  hour: number;
  name?: string;
}) {
  return apiRequest<{ batch_id?: string; batch?: Record<string, unknown> }>(
    `/t/${tenantId}/batches`,
    { method: "POST", body },
  );
}

export async function refreshTokens() {
  return refreshAccessToken();
}

export async function getMe() {
  return apiRequest<{
    account_id: string;
    tenant_id: string;
    account: Record<string, unknown>;
    linked: boolean;
  }>("/me");
}

// ── Sync endpoints (for connectivity pill) ───────────────────────────

export async function syncPull(params: {
  since_seq?: number;
  limit?: number;
  device_id?: string;
} = {}) {
  setSyncState("syncing");
  try {
    const result = await apiRequest<{
      operations?: unknown[];
      next_seq?: number;
      conflicts?: unknown[];
    }>("/sync/pull", {
      method: "POST",
      body: {
        since_seq: params.since_seq ?? 0,
        limit: params.limit ?? 200,
        device_id: params.device_id ?? "",
      },
    });
    if (result.conflicts && Array.isArray(result.conflicts) && result.conflicts.length > 0) {
      setSyncState("conflict");
    } else {
      setSyncState("synced");
    }
    return result;
  } catch (err) {
    const apiErr = err as ApiError;
    if (apiErr.status === 0) setSyncState("offline");
    else setSyncState("offline");
    throw err;
  }
}

export async function syncPush(params: {
  operations: unknown[];
  device_id?: string;
}) {
  setSyncState("syncing");
  try {
    const result = await apiRequest("/sync/push", {
      method: "POST",
      body: {
        operations: params.operations,
        device_id: params.device_id ?? "",
      },
    });
    setSyncState("synced");
    return result;
  } catch (err) {
    setSyncState("offline");
    throw err;
  }
}

export async function healthCheck(): Promise<boolean> {
  try {
    await apiRequest("/health", { skipAuth: true });
    if (currentSyncState === "offline") setSyncState("synced");
    return true;
  } catch {
    setSyncState("offline");
    return false;
  }
}

// Poll connectivity for the pill (call from shell)
let pollTimer: ReturnType<typeof setInterval> | null = null;

export function startConnectivityPoll(intervalMs = 30000) {
  stopConnectivityPoll();
  healthCheck();
  pollTimer = setInterval(() => {
    healthCheck().catch(() => {});
  }, intervalMs);
}

export function stopConnectivityPoll() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

// ── Attendance (Portion 12) ──────────────────────────────────────────

export function tenantPath(tenantId: string, suffix: string) {
  return `/t/${tenantId}${suffix.startsWith("/") ? suffix : `/${suffix}`}`;
}

export async function getBatchAttendance(tenantId: string, batchId: string, onDate: string) {
  return apiRequest<{ date: string; batch_id: string; rows: AttendanceRow[] }>(
    tenantPath(tenantId, `/attendance/batch/${batchId}?on_date=${encodeURIComponent(onDate)}`)
  );
}

export async function getAbsentees(
  tenantId: string,
  batchId: string,
  onDate: string,
  daysBack = 1
) {
  return apiRequest<{ batch_id: string; days: AbsenteeDay[] }>(
    tenantPath(
      tenantId,
      `/attendance/absentees?batch_id=${encodeURIComponent(batchId)}&on_date=${encodeURIComponent(onDate)}&days_back=${daysBack}`
    )
  );
}

export async function listAttendanceReviews(tenantId: string, limit = 100) {
  return apiRequest<{ reviews: ReviewFlag[] }>(
    tenantPath(tenantId, `/attendance/reviews?limit=${limit}`)
  );
}

export async function resolveAttendanceReview(
  tenantId: string,
  flagId: string,
  finalStatus: string,
  notes = ""
) {
  return apiRequest<{ resolved: boolean; flag_id: string; final_status: string }>(
    tenantPath(tenantId, `/attendance/reviews/${flagId}/resolve`),
    { method: "POST", body: { final_status: finalStatus, notes } }
  );
}

export async function markManualAttendance(
  tenantId: string,
  params: {
    student_id: string;
    on_date: string;
    status_or_time: string;
    batch_id?: string;
    notes?: string;
  }
) {
  return apiRequest<{ punch_or_record_id: string }>(
    tenantPath(tenantId, "/attendance/manual"),
    { method: "POST", body: params }
  );
}

// ── Admission (Portion 13) ───────────────────────────────────────────

export async function listBatches(tenantId: string, activeOnly = true) {
  return apiRequest<{ batches: BatchRow[] }>(
    tenantPath(tenantId, `/batches?active_only=${activeOnly}`)
  );
}

export async function listStudentsApi(tenantId: string) {
  return apiRequest<{ students: StudentRow[] }>(tenantPath(tenantId, "/students"));
}

export async function checkDuplicates(
  tenantId: string,
  params: {
    name: string;
    student_phone?: string;
    parent_phones?: string[];
    exclude_id?: string;
  }
) {
  return apiRequest<{ matches: DuplicateMatch[] }>(
    tenantPath(tenantId, "/students/duplicate-check"),
    { method: "POST", body: params }
  );
}

export async function previewRoll(tenantId: string, batchId: string, serial?: number) {
  return apiRequest<{ batch_id: string; days: string[]; hour: number; serial: number; roll: string }>(
    tenantPath(tenantId, "/students/roll-preview"),
    { method: "POST", body: { batch_id: batchId, serial } }
  );
}

export async function admitStudent(
  tenantId: string,
  params: {
    name: string;
    batch_id: string;
    student_phone?: string;
    parent_phones?: string[];
    whatsapp?: string;
    roll?: string;
    custom_fields?: Record<string, unknown>;
    force?: boolean;
  }
) {
  return apiRequest<{ student_id: string; join_code?: string } | { detail: string; matches: DuplicateMatch[] }>(
    tenantPath(tenantId, "/students"),
    { method: "POST", body: params }
  );
}

export async function migrateStudent(
  tenantId: string,
  studentId: string,
  params: { new_batch_id?: string; new_roll?: string }
) {
  return apiRequest<{ migration: MigrationResult }>(
    tenantPath(tenantId, `/students/${studentId}/migrate`),
    { method: "POST", body: params }
  );
}

export async function listTemplates(tenantId: string) {
  return apiRequest<{ templates: TemplateRow[] }>(tenantPath(tenantId, "/templates"));
}

// ── Shared domain types ──────────────────────────────────────────────

export interface AttendanceRow {
  student_id: string;
  name?: string;
  roll?: string;
  status: string;
  late_minutes?: number | null;
  flags?: string[];
  record?: {
    status?: string;
    source_precedence?: string;
    flags?: string[];
    is_reviewed?: boolean;
    cross_batch?: boolean;
    [key: string]: unknown;
  };
}

export interface AbsenteeDay {
  date: string;
  absentees: AttendanceRow[];
  count: number;
}

export interface ReviewFlag {
  id: string;
  student_id: string;
  date: string;
  flag_type?: string;
  is_resolved?: boolean;
  [key: string]: unknown;
}

export interface BatchRow {
  id: string;
  name?: string;
  days?: string[];
  hour?: number;
  display_name?: string;
  is_active?: boolean;
  [key: string]: unknown;
}

export interface StudentRow {
  id: string;
  name?: string;
  roll?: string;
  batch_id?: string;
  student_phone?: string;
  parent_phones?: string[];
  custom_fields?: Record<string, unknown>;
  is_active?: boolean;
  [key: string]: unknown;
}

export interface DuplicateMatch {
  student_id: string;
  name: string;
  roll: string;
  student_phone: string;
  reason: string;
}

export interface MigrationResult {
  id?: string;
  student_id: string;
  old_roll: string;
  new_roll: string;
  old_batch_id: string;
  new_batch_id: string;
  tables_migrated: string[];
  records_moved: number;
  status: string;
  error_message?: string | null;
}

export interface TemplateRow {
  id: string;
  name?: string;
  coaching_type?: string;
  default_days?: string[];
  default_hour?: number;
  [key: string]: unknown;
}

// ── Batch config (Portion 14) ────────────────────────────────────────

export async function getBatchDetail(tenantId: string, batchId: string) {
  return apiRequest<{
    batch: BatchRow & { extra_sessions?: ExtraSession[] };
    late_threshold: { global_minutes: number; batch_minutes: number; has_override: boolean };
    irregularity_threshold: { global_days: number; batch_days: number; has_override: boolean };
  }>(tenantPath(tenantId, `/batches/${batchId}`));
}

export async function updateBatch(
  tenantId: string,
  batchId: string,
  body: { days?: string[]; hour?: number; name_override?: string; is_active?: boolean }
) {
  return apiRequest<{ updated: boolean; batch: BatchRow }>(
    tenantPath(tenantId, `/batches/${batchId}`),
    { method: "PATCH", body }
  );
}

export async function setLateThreshold(
  tenantId: string,
  minutes: number,
  batchId?: string
) {
  return apiRequest<{ minutes: number; batch_id?: string; effective: number; global: number }>(
    tenantPath(tenantId, "/attendance/late-threshold"),
    { method: "PUT", body: { minutes, batch_id: batchId || null } }
  );
}

export async function addExtraSession(
  tenantId: string,
  batchId: string,
  body: { day: string; hour: number; expires_on: string }
) {
  return apiRequest<{ batch: BatchRow & { extra_sessions?: ExtraSession[] } }>(
    tenantPath(tenantId, `/batches/${batchId}/extra-sessions`),
    { method: "POST", body: { batch_id: batchId, ...body } }
  );
}

// ── Payments (Portion 15) ────────────────────────────────────────────

export async function getBatchPayments(
  tenantId: string,
  batchId: string,
  year: number,
  month: number
) {
  return apiRequest<{ batch_id: string; year: number; month: number; rows: PaymentRow[] }>(
    tenantPath(tenantId, `/payments/batch/${batchId}?year=${year}&month=${month}`)
  );
}

export async function markPaid(
  tenantId: string,
  params: {
    student_id: string;
    year: number;
    month: number;
    amount?: number;
    receipt_ref?: string;
    notes?: string;
  }
) {
  return apiRequest<{ payment: Record<string, unknown> }>(
    tenantPath(tenantId, "/payments/mark-paid"),
    { method: "POST", body: params }
  );
}

export async function lockPayment(
  tenantId: string,
  params: { student_id: string; year: number; month: number }
) {
  return apiRequest<{ payment: Record<string, unknown> }>(
    tenantPath(tenantId, "/payments/lock"),
    { method: "POST", body: params }
  );
}

export async function unlockPayment(
  tenantId: string,
  params: {
    student_id: string;
    year: number;
    month: number;
    reason?: string;
    is_owner?: boolean;
  }
) {
  return apiRequest<{ payment: Record<string, unknown> }>(
    tenantPath(tenantId, "/payments/unlock"),
    { method: "POST", body: { is_owner: true, ...params } }
  );
}

export async function setNotifyFlag(
  tenantId: string,
  params: { student_id: string; year: number; month: number; flag: "green" | "white" }
) {
  return apiRequest<{ payment: Record<string, unknown> }>(
    tenantPath(tenantId, "/payments/notify-flag"),
    { method: "POST", body: params }
  );
}

export async function getDelayedCandidates(
  tenantId: string,
  batchId: string,
  year: number,
  month: number
) {
  return apiRequest<{
    year: number;
    month: number;
    batch_id: string;
    will_notify: PaymentRow[];
    suppressed_white: PaymentRow[];
    excluded_irregular: PaymentRow[];
    links: Record<string, string>;
  }>(tenantPath(tenantId, `/payments/delayed/${batchId}?year=${year}&month=${month}`));
}

export interface ExtraSession {
  day: string;
  hour: number;
  expires_on: string;
}

export interface PaymentRow {
  student_id: string;
  name?: string;
  roll?: string;
  status: string;
  locked: boolean;
  notify_flag?: string;
  amount?: number | null;
  record?: Record<string, unknown>;
}

// ── Exams (Portion 16) ───────────────────────────────────────────────

export async function listExamTemplates(tenantId: string) {
  return apiRequest<{ templates: ExamTemplateRow[] }>(tenantPath(tenantId, "/exam-templates"));
}

export async function createExam(
  tenantId: string,
  body: {
    name: string;
    exam_date: string;
    batch_id?: string;
    template_id?: string;
    chapter_or_topic?: string;
    subject?: string;
    sections?: unknown[];
    is_ad_hoc?: boolean;
    notes?: string;
  }
) {
  return apiRequest<{ exam_id: string; exam: ExamRow }>(tenantPath(tenantId, "/exams"), {
    method: "POST",
    body,
  });
}

export async function listExams(tenantId: string, batchId?: string, status?: string) {
  const q = new URLSearchParams();
  if (batchId) q.set("batch_id", batchId);
  if (status) q.set("status", status);
  const qs = q.toString() ? `?${q}` : "";
  return apiRequest<{ exams: ExamRow[] }>(tenantPath(tenantId, `/exams${qs}`));
}

export async function getExam(tenantId: string, examId: string) {
  return apiRequest<{ exam: ExamRow }>(tenantPath(tenantId, `/exams/${examId}`));
}

export async function enterResult(
  tenantId: string,
  examId: string,
  body: {
    student_id: string;
    section_scores?: { key: string; marks_obtained: number; max_marks?: number }[];
    is_absent?: boolean;
    notes?: string;
  }
) {
  return apiRequest<{ result: ExamResultRow }>(
    tenantPath(tenantId, `/exams/${examId}/results`),
    { method: "POST", body }
  );
}

export async function getExamResults(tenantId: string, examId: string) {
  return apiRequest<{ results: ExamResultRow[] }>(
    tenantPath(tenantId, `/exams/${examId}/results`)
  );
}

export async function getStudentResults(tenantId: string, studentId: string) {
  return apiRequest<{ results: ExamResultRow[] }>(
    tenantPath(tenantId, `/students/${studentId}/results`)
  );
}

export async function getExamSummary(tenantId: string, examId: string) {
  return apiRequest<ExamSummary>(tenantPath(tenantId, `/exams/${examId}/summary`));
}

export async function getTopicHeatmap(tenantId: string, batchId?: string) {
  const qs = batchId ? `?batch_id=${encodeURIComponent(batchId)}` : "";
  return apiRequest<{ topics: HeatmapTopic[] }>(
    tenantPath(tenantId, `/analytics/heatmap${qs}`)
  );
}

export async function getStruggleList(tenantId: string, batchId: string) {
  return apiRequest<{ students: StruggleRow[] }>(
    tenantPath(tenantId, `/analytics/struggle?batch_id=${encodeURIComponent(batchId)}`)
  );
}

export async function completeExam(tenantId: string, examId: string) {
  return apiRequest<{ completed: boolean; exam: ExamRow }>(
    tenantPath(tenantId, `/exams/${examId}/complete`),
    { method: "POST", body: {} }
  );
}

// ── Vault (Portion 17) ───────────────────────────────────────────────

export async function listVault(tenantId: string, topic?: string, batchId?: string) {
  const q = new URLSearchParams();
  if (topic) q.set("topic", topic);
  if (batchId) q.set("batch_id", batchId);
  const qs = q.toString() ? `?${q}` : "";
  return apiRequest<{ resources: VaultResource[] }>(tenantPath(tenantId, `/vault${qs}`));
}

export async function createVaultResource(
  tenantId: string,
  body: {
    title: string;
    resource_type?: string;
    topic?: string;
    subject?: string;
    description?: string;
    url?: string;
    batch_ids?: string[];
    access_rules?: { operator: string; rules: AccessRuleRow[] };
    protection_level?: string;
    actor_role?: string;
  }
) {
  return apiRequest<{ resource_id: string; resource: VaultResource }>(
    tenantPath(tenantId, "/vault"),
    { method: "POST", body }
  );
}

export async function setVaultAccessRules(
  tenantId: string,
  resourceId: string,
  operator: string,
  rules: AccessRuleRow[]
) {
  return apiRequest<{ resource: VaultResource }>(
    tenantPath(tenantId, `/vault/${resourceId}/access-rules`),
    { method: "PUT", body: { operator, rules } }
  );
}

export async function relaxVaultProtection(
  tenantId: string,
  resourceId: string,
  actorRole = "owner"
) {
  return apiRequest<{ resource: VaultResource }>(
    tenantPath(tenantId, `/vault/${resourceId}/relax`),
    { method: "POST", body: { actor_role: actorRole } }
  );
}

export async function restoreVaultProtection(
  tenantId: string,
  resourceId: string,
  actorRole = "owner"
) {
  return apiRequest<{ resource: VaultResource }>(
    tenantPath(tenantId, `/vault/${resourceId}/restore`),
    { method: "POST", body: { actor_role: actorRole } }
  );
}

export interface ExamTemplateRow {
  id: string;
  name?: string;
  sections?: { key: string; name: string; section_type: string; max_marks: number }[];
  is_default?: boolean;
  [key: string]: unknown;
}

export interface ExamRow {
  id: string;
  name?: string;
  exam_date?: string;
  batch_id?: string;
  template_id?: string;
  chapter_or_topic?: string;
  subject?: string;
  status?: string;
  is_ad_hoc?: boolean;
  sections?: { key: string; name: string; section_type: string; max_marks: number }[];
  [key: string]: unknown;
}

export interface ExamResultRow {
  id?: string;
  exam_id?: string;
  student_id?: string;
  roll?: string;
  percentage?: number;
  total_obtained?: number;
  is_absent?: boolean;
  section_scores?: { key: string; marks_obtained: number; max_marks: number }[];
  chapter_or_topic?: string;
  exam_date?: string;
  [key: string]: unknown;
}

export interface ExamSummary {
  exam_id: string;
  exam_name?: string;
  n_present?: number;
  n_absent?: number;
  mean_percentage?: number | null;
  median_percentage?: number | null;
  section_averages?: Record<string, number>;
  [key: string]: unknown;
}

export interface HeatmapTopic {
  chapter_or_topic: string;
  n: number;
  mean_percentage: number;
  median_percentage: number;
  min_percentage: number;
  max_percentage: number;
}

export interface StruggleRow {
  student_id: string;
  name?: string;
  roll?: string;
  recent_avg_percentage?: number | null;
  attended_days_this_month?: number | null;
  reason?: string;
}

export interface AccessRuleRow {
  kind: string;
  value?: string | number;
}

export interface VaultResource {
  id: string;
  title?: string;
  resource_type?: string;
  topic?: string;
  subject?: string;
  protection_level?: string;
  access_rules?: { operator?: string; rules?: AccessRuleRow[] };
  watermark?: boolean;
  no_download?: boolean;
  is_active?: boolean;
  [key: string]: unknown;
}

// ── Staff & Settings (Portion 18) ────────────────────────────────────

export async function listStaff(tenantId: string) {
  return apiRequest<{ staff: StaffRow[]; roles: RoleRow[] }>(tenantPath(tenantId, "/staff"));
}

export async function listRoles(tenantId: string) {
  return apiRequest<{ roles: RoleRow[] }>(tenantPath(tenantId, "/roles"));
}

export async function createStaff(
  tenantId: string,
  body: { username: string; role_name: string; email?: string; phone?: string }
) {
  return apiRequest<{ user_id: string; user: StaffRow }>(tenantPath(tenantId, "/staff"), {
    method: "POST",
    body,
  });
}

export async function assignStaffRole(
  tenantId: string,
  userId: string,
  roleName: string,
  isOwner = true
) {
  return apiRequest<{ user: StaffRow; role_name: string }>(
    tenantPath(tenantId, `/staff/${userId}/role`),
    { method: "POST", body: { role_name: roleName, is_owner: isOwner } }
  );
}

export async function getCentreMode(tenantId: string) {
  return apiRequest<{ mode: string; runtime_mode: string; options: string[] }>(
    tenantPath(tenantId, "/settings/mode")
  );
}

export async function setCentreMode(tenantId: string, mode: string) {
  return apiRequest<{ mode: string; runtime_mode: string }>(
    tenantPath(tenantId, "/settings/mode"),
    { method: "PUT", body: { mode } }
  );
}

export async function getMessagingSettings(tenantId: string) {
  return apiRequest<{
    channels: Record<string, boolean>;
    cost_cap?: number | null;
    templates: Record<string, string>;
    provider_channels?: unknown[];
  }>(tenantPath(tenantId, "/settings/messaging"));
}

export async function putMessagingSettings(
  tenantId: string,
  body: {
    channels?: Record<string, boolean>;
    cost_cap?: number;
    templates?: Record<string, string>;
  }
) {
  return apiRequest<{
    channels: Record<string, boolean>;
    cost_cap?: number | null;
    templates: Record<string, string>;
  }>(tenantPath(tenantId, "/settings/messaging"), { method: "PUT", body });
}

// ── Teacher AI review & threads (Portion 19) ─────────────────────────

export async function listAiReviewQueue(tenantId: string, status = "needs_review") {
  return apiRequest<{ items: AiReviewItem[] }>(
    tenantPath(tenantId, `/ai/review-queue?status=${encodeURIComponent(status)}`)
  );
}

export async function approveAiItem(
  tenantId: string,
  itemId: string,
  edits?: Record<string, unknown>
) {
  return apiRequest<{ item: AiReviewItem }>(
    tenantPath(tenantId, `/ai/review-queue/${itemId}/approve`),
    { method: "POST", body: { edits } }
  );
}

export async function rejectAiItem(tenantId: string, itemId: string, reason = "") {
  return apiRequest<{ item: AiReviewItem }>(
    tenantPath(tenantId, `/ai/review-queue/${itemId}/reject`),
    { method: "POST", body: { reason } }
  );
}

export async function listFlaggedThreads(tenantId: string) {
  return apiRequest<{ threads: FlaggedThread[] }>(
    tenantPath(tenantId, "/ai/threads/flagged")
  );
}

export async function getThreadMessages(tenantId: string, threadId: string) {
  return apiRequest<{ thread: FlaggedThread | null; messages: ThreadMessage[] }>(
    tenantPath(tenantId, `/ai/threads/${threadId}/messages`)
  );
}

export async function takeOverThread(
  tenantId: string,
  threadId: string,
  content: string,
  studentId = ""
) {
  return apiRequest<{ message: ThreadMessage }>(
    tenantPath(tenantId, `/ai/threads/${threadId}/take-over`),
    { method: "POST", body: { content, student_id: studentId } }
  );
}

export interface StaffRow {
  id: string;
  username?: string;
  email?: string;
  phone?: string;
  role_id?: string;
  role_name?: string;
  is_active?: boolean;
  [key: string]: unknown;
}

export interface RoleRow {
  id: string;
  name?: string;
  description?: string;
  is_system?: boolean;
}

export interface AiReviewItem {
  id: string;
  status?: string;
  subject?: string;
  topic?: string;
  grounded?: boolean;
  confidence?: number;
  impact_score?: number;
  review_reason?: string;
  content?: {
    answer?: string;
    how?: string;
    why?: string;
    question?: string;
    source_chunks?: { text?: string; ref?: string }[];
    [key: string]: unknown;
  };
  source_chunks?: { text?: string; ref?: string }[];
  history?: unknown[];
  [key: string]: unknown;
}

export interface FlaggedThread {
  id: string;
  student_id?: string;
  subject?: string;
  topic?: string;
  title?: string;
  flagged_for_teacher?: boolean;
  min_confidence?: number;
  priority?: number;
  message_count?: number;
  [key: string]: unknown;
}

export interface ThreadMessage {
  id?: string;
  role?: string;
  content?: string;
  confidence?: number;
  grounded?: boolean;
  needs_review?: boolean;
  source_chunks?: { text?: string; ref?: string }[];
  teacher_annotation?: string;
  created_at?: string;
  [key: string]: unknown;
}

// ── Teacher AI Co-Pilot (Portion 20) ─────────────────────────────────

export async function listStyleProfiles(tenantId: string) {
  return apiRequest<{ profiles: StyleProfile[] }>(
    tenantPath(tenantId, "/ai/style-profiles")
  );
}

export async function getStyleProfile(tenantId: string, subject: string) {
  return apiRequest<{ profile: StyleProfile }>(
    tenantPath(tenantId, `/ai/style-profiles/${encodeURIComponent(subject)}`)
  );
}

export async function upsertStyleProfile(
  tenantId: string,
  body: {
    subject: string;
    style_notes?: string;
    terminology?: string[];
    sign_conventions?: string;
    difficulty?: string;
    few_shot_examples?: { input?: string; output?: string }[];
    preferred_language?: string;
  }
) {
  return apiRequest<{ profile: StyleProfile }>(
    tenantPath(tenantId, "/ai/style-profiles"),
    { method: "PUT", body }
  );
}

export async function listItemBank(tenantId: string, subject = "", topic = "") {
  const q = new URLSearchParams();
  if (subject) q.set("subject", subject);
  if (topic) q.set("topic", topic);
  const qs = q.toString() ? `?${q}` : "";
  return apiRequest<{ items: ItemBankRow[] }>(
    tenantPath(tenantId, `/ai/item-bank${qs}`)
  );
}

export async function getItemHistory(tenantId: string, itemId: string) {
  return apiRequest<{
    item_id: string;
    status?: string;
    version?: number;
    history: ItemHistoryEntry[];
    source_chunks?: { text?: string; ref?: string }[];
  }>(tenantPath(tenantId, `/ai/items/${itemId}/history`));
}

export async function pushItemToBank(tenantId: string, itemId: string) {
  return apiRequest<{ item: ItemBankRow }>(
    tenantPath(tenantId, `/ai/items/${itemId}/push-bank`),
    { method: "POST", body: {} }
  );
}

export async function ocrAssist(tenantId: string, imageRef: string, rubric?: Record<string, unknown>) {
  return apiRequest<{
    result: {
      ok: boolean;
      status?: string;
      message?: string;
      transcription?: string | null;
      grade?: unknown;
      conceptual_flags?: unknown[];
    };
    beta: boolean;
    implemented: boolean;
  }>(tenantPath(tenantId, "/ai/ocr"), {
    method: "POST",
    body: { image_ref: imageRef, rubric },
  });
}

export async function generateRecapDraft(
  tenantId: string,
  body: {
    subject: string;
    topic: string;
    cohort_size?: number;
    weakness_severity?: number;
  }
) {
  return apiRequest<{
    item: AiReviewItem;
    queued_for_review: boolean;
    review_path: string;
  }>(tenantPath(tenantId, "/ai/recap-draft"), { method: "POST", body });
}

export interface StyleProfile {
  id?: string;
  subject?: string;
  style_notes?: string;
  terminology?: string[];
  sign_conventions?: string;
  difficulty?: string;
  few_shot_examples?: { input?: string; output?: string }[];
  preferred_language?: string;
  version?: number;
  [key: string]: unknown;
}

export interface ItemBankRow {
  id: string;
  subject?: string;
  topic?: string;
  status?: string;
  provenance?: "ai_approved" | "teacher_authored" | string;
  in_exam_bank?: boolean;
  content?: Record<string, unknown>;
  confidence?: number;
  version?: number;
  history?: ItemHistoryEntry[];
  [key: string]: unknown;
}

export interface ItemHistoryEntry {
  action?: string;
  at?: string;
  by?: string;
  status?: string;
  reason?: string;
}

// ── Student / Parent core (Portion 21) ────────────────────────────────

export async function createStudentAccount(
  tenantId: string,
  body: { role?: string; phone?: string; email?: string; display_name?: string }
) {
  return apiRequest<{ account: StudentAccount }>(tenantPath(tenantId, "/accounts"), {
    method: "POST",
    body: { role: "student", ...body },
  });
}

export async function linkByJoinCode(
  tenantId: string,
  accountId: string,
  joinCode: string
) {
  return apiRequest<{
    linked: boolean;
    admission_id: string;
    account_id: string;
    student_name?: string;
    roll?: string;
  }>(tenantPath(tenantId, "/accounts/link-join"), {
    method: "POST",
    body: { account_id: accountId, join_code: joinCode },
  });
}

export async function getStudentHome(tenantId: string, accountId: string) {
  return apiRequest<StudentHomeView>(
    tenantPath(tenantId, `/accounts/${accountId}/home`)
  );
}

export async function solveAsk(
  tenantId: string,
  body: {
    student_id: string;
    question: string;
    subject?: string;
    topic?: string;
    board?: string;
    thread_id?: string;
    batch_id?: string;
  }
) {
  return apiRequest<SolveResponse>(tenantPath(tenantId, "/solve/ask"), {
    method: "POST",
    body,
  });
}

export async function listStudentThreads(tenantId: string, studentId: string) {
  return apiRequest<{ threads: FlaggedThread[] }>(
    tenantPath(tenantId, `/solve/threads?student_id=${encodeURIComponent(studentId)}`)
  );
}

export async function getStudentThreadMessages(tenantId: string, threadId: string) {
  return apiRequest<{ thread: FlaggedThread | null; messages: ThreadMessage[] }>(
    tenantPath(tenantId, `/solve/threads/${threadId}/messages`)
  );
}

export async function replyStudentThread(
  tenantId: string,
  threadId: string,
  studentId: string,
  content: string
) {
  return apiRequest<SolveResponse>(
    tenantPath(tenantId, `/solve/threads/${threadId}/reply`),
    { method: "POST", body: { student_id: studentId, content } }
  );
}

export async function getStudentResultsHistory(tenantId: string, studentId: string) {
  return apiRequest<{ results: ExamResultRow[] }>(
    tenantPath(tenantId, `/students/${studentId}/results`)
  );
}

export async function listStudentVault(tenantId: string, studentId: string) {
  return apiRequest<{
    items: {
      resource: VaultResource;
      allowed: boolean;
      reasons: string[];
    }[];
  }>(tenantPath(tenantId, `/vault/student?student_id=${encodeURIComponent(studentId)}`));
}

export async function evaluateVaultAccess(
  tenantId: string,
  resourceId: string,
  studentId: string
) {
  return apiRequest<{
    allowed: boolean;
    reasons: string[];
    resource_id: string;
    student_id: string;
  }>(
    tenantPath(
      tenantId,
      `/vault/${resourceId}/access?student_id=${encodeURIComponent(studentId)}`
    )
  );
}

export interface StudentAccount {
  id: string;
  role?: string;
  phone?: string;
  email?: string;
  display_name?: string;
  primary_admission_id?: string;
  [key: string]: unknown;
}

export interface StudentHomeView {
  account_id: string;
  admission_id: string;
  student?: {
    id?: string;
    name?: string;
    roll?: string;
    batch_id?: string;
    [key: string]: unknown;
  };
  attendance?: { status?: string; date?: string; [key: string]: unknown }[];
  payments?: { status?: string; year?: number; month?: number; [key: string]: unknown }[];
  results?: ExamResultRow[];
  threads?: FlaggedThread[];
}

export interface SolveResponse {
  ok?: boolean;
  error?: string;
  message?: string;
  answer?: string;
  how?: string;
  why?: string;
  confidence?: number;
  grounded?: boolean;
  needs_review?: boolean;
  review_reason?: string;
  thread_id?: string;
  message_id?: string;
  subject?: string;
  topic?: string;
  cached?: boolean;
  [key: string]: unknown;
}

// ── Parent portal (Portion 22) ────────────────────────────────────────

export async function getParentPortal(tenantId: string, parentId: string) {
  return apiRequest<{
    parent_account_id: string;
    children: ParentChild[];
    tenant_id: string;
    centre_name: string;
    centre_id?: string;
  }>(tenantPath(tenantId, `/parents/${parentId}`));
}

export async function linkParentToStudent(
  tenantId: string,
  parentAccountId: string,
  studentId: string
) {
  return apiRequest<{ link: Record<string, unknown> }>(
    tenantPath(tenantId, "/parents/link"),
    {
      method: "POST",
      body: { parent_account_id: parentAccountId, student_id: studentId },
    }
  );
}

export async function getParentStudentSummary(
  tenantId: string,
  parentId: string,
  studentId: string
) {
  return apiRequest<{
    tenant_id: string;
    parent_id: string;
    student_id: string;
    student?: { name?: string; roll?: string; [key: string]: unknown };
    attendance?: { status?: string; date?: string; [key: string]: unknown }[];
    payments?: { status?: string; year?: number; month?: number; [key: string]: unknown }[];
    results?: ExamResultRow[];
  }>(tenantPath(tenantId, `/parents/${parentId}/students/${studentId}/summary`));
}

export async function getParentNotifications(
  tenantId: string,
  parentId: string,
  studentId?: string
) {
  const q = studentId ? `?student_id=${encodeURIComponent(studentId)}` : "";
  return apiRequest<{
    notifications: ParentNotification[];
    scoped_student_id?: string;
  }>(tenantPath(tenantId, `/parents/${parentId}/notifications${q}`));
}

export async function getParentPreferences(tenantId: string, parentId: string) {
  return apiRequest<{
    preferences: NotifPref[];
    event_types: string[];
    channels: string[];
  }>(tenantPath(tenantId, `/parents/${parentId}/preferences`));
}

export async function setParentPreference(
  tenantId: string,
  parentId: string,
  body: {
    user_id: string;
    student_id?: string;
    channel_type: string;
    event_type: string;
    enabled: boolean;
  }
) {
  return apiRequest<{ preference_id: string; event_type: string; enabled: boolean }>(
    tenantPath(tenantId, `/parents/${parentId}/preferences`),
    { method: "PUT", body }
  );
}

export interface ParentChild {
  student_id: string;
  link_id?: string;
  student?: {
    id?: string;
    name?: string;
    roll?: string;
    batch_id?: string;
    [key: string]: unknown;
  };
}

export interface ParentNotification {
  id?: string;
  student_id?: string;
  event_type?: string;
  channel_type?: string;
  subject?: string;
  content?: string;
  created_at?: string;
  [key: string]: unknown;
}

export interface NotifPref {
  user_id?: string;
  channel_type?: string;
  event_type?: string;
  enabled?: boolean;
  [key: string]: unknown;
}

// ── Founder super-admin (Portion 23) ──────────────────────────────────

const FOUNDER_TOKEN_KEY = "cohortos_founder_token";

export function loadFounderToken(): string {
  const t = (typeof localStorage !== "undefined" && localStorage.getItem(FOUNDER_TOKEN_KEY)) || "";
  if (!t) {
    // Prefer env injected at build time; never fall back to a known string
    const fromEnv = (import.meta as any).env?.VITE_FOUNDER_TOKEN || "";
    if (!fromEnv) throw new Error("Founder token not configured (set VITE_FOUNDER_TOKEN or call saveFounderToken)");
    return fromEnv;
  }
  return t;
}

export function saveFounderToken(token: string) {
  localStorage.setItem(FOUNDER_TOKEN_KEY, token);
}

async function founderRequest<T>(
  path: string,
  options: { method?: string; body?: unknown } = {}
): Promise<T> {
  const base = getApiBaseUrl();
  const url = `${base}${path.startsWith("/") ? path : `/${path}`}`;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "X-Founder-Token": loadFounderToken(),
  };
  const tokens = loadTokens();
  if (tokens.access_token) headers.Authorization = `Bearer ${tokens.access_token}`;

  let response: Response;
  try {
    response = await fetch(url, {
      method: options.method || "GET",
      headers,
      body: options.body != null ? JSON.stringify(options.body) : undefined,
    });
  } catch {
    const error: ApiError = { status: 0, detail: "Network unavailable" };
    throw error;
  }
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const j = await response.json();
      detail = j.detail || detail;
    } catch {
      /* */
    }
    const error: ApiError = { status: response.status, detail };
    throw error;
  }
  if (response.status === 204) return {} as T;
  return response.json() as Promise<T>;
}

export async function founderDashboard() {
  return founderRequest<{
    tenant_count: number;
    active: number;
    suspended: number;
    trial: number;
    tenants: FounderTenantSummary[];
  }>("/founder/dashboard");
}

export async function founderListTenants(status?: string) {
  const q = status ? `?status=${encodeURIComponent(status)}` : "";
  return founderRequest<{ tenants: FounderTenant[] }>(`/founder/tenants${q}`);
}

export async function founderGetTenant(tenantId: string) {
  return founderRequest<{ tenant: FounderTenant; metrics: AiMetrics }>(
    `/founder/tenants/${tenantId}`
  );
}

export async function founderProvision(body: {
  name: string;
  code: string;
  owner_email?: string;
  owner_phone?: string;
  mode?: string;
  tier?: string;
  student_count?: number;
  trial_days?: number;
}) {
  return founderRequest<{ tenant: FounderTenant }>("/founder/tenants", {
    method: "POST",
    body,
  });
}

export async function founderSuspend(tenantId: string, reason = "") {
  return founderRequest<{ tenant: FounderTenant }>(
    `/founder/tenants/${tenantId}/suspend`,
    { method: "POST", body: { reason } }
  );
}

export async function founderExtend(tenantId: string, days = 30) {
  return founderRequest<{ tenant: FounderTenant }>(
    `/founder/tenants/${tenantId}/extend`,
    { method: "POST", body: { days } }
  );
}

export async function founderActivate(tenantId: string) {
  return founderRequest<{ tenant: FounderTenant }>(
    `/founder/tenants/${tenantId}/activate`,
    { method: "POST", body: {} }
  );
}

export async function founderUpdateStudentCount(tenantId: string, studentCount: number) {
  return founderRequest<{ tenant: FounderTenant }>(
    `/founder/tenants/${tenantId}/student-count`,
    { method: "PUT", body: { student_count: studentCount } }
  );
}

export async function founderPricingTiers() {
  return founderRequest<{
    tiers: { id: string; limit: number; base_price_bdt: number }[];
  }>("/founder/pricing/tiers");
}

export async function founderQuote(body: {
  student_count: number;
  tier?: string;
  billing_cycle?: string;
}) {
  return founderRequest<{ quote: Record<string, unknown> }>("/founder/pricing/quote", {
    method: "POST",
    body,
  });
}

export async function founderAudit(limit = 50) {
  return founderRequest<{ audit: FounderAuditEntry[] }>(`/founder/audit?limit=${limit}`);
}

export interface AiMetrics {
  query_volume?: number;
  rate_limit_hits?: number;
  cache_hit_rate?: number;
  mcq_count?: number;
  written_count?: number;
  cache_hits?: number;
  cache_misses?: number;
  period?: string;
  [key: string]: unknown;
}

export interface FounderTenant {
  id: string;
  name?: string;
  code?: string;
  status?: string;
  tier?: string;
  mode?: string;
  student_count?: number;
  trial_ends_at?: string;
  extended_until?: string;
  suspended_reason?: string;
  owner_email?: string;
  [key: string]: unknown;
}

export interface FounderTenantSummary {
  tenant_id: string;
  name?: string;
  code?: string;
  status?: string;
  tier?: string;
  student_count?: number;
  metrics?: AiMetrics;
}

export interface FounderAuditEntry {
  action?: string;
  tenant_id?: string;
  created_at?: string;
  detail?: Record<string, unknown>;
  [key: string]: unknown;
}



// ── Sync conflicts / Backup / License (Batch 2) ─────────────────────

export async function listSyncConflicts(tenantId: string) {
  return apiRequest<{ conflicts: SyncConflictRow[] }>(
    tenantPath(tenantId, "/sync/conflicts")
  );
}

export async function resolveSyncConflict(
  tenantId: string,
  conflictId: number,
  resolution: string,
  notes = ""
) {
  return apiRequest<{ ok: boolean }>(
    tenantPath(tenantId, `/sync/conflicts/${conflictId}/resolve`),
    { method: "POST", body: { resolution, notes } }
  );
}

export async function getBackupStatus(tenantId: string) {
  return apiRequest<{
    db_path: string;
    wal_active: boolean;
    journal_mode: string;
    backups: { path: string; name: string; size: number }[];
    backup_dir: string | null;
  }>(tenantPath(tenantId, "/backup/status"));
}

export async function triggerBackupExport(tenantId: string) {
  return apiRequest<{
    ok: boolean;
    snapshot_path: string | null;
    export: { tenant_id: string; tables: Record<string, unknown[]> };
    message: string;
  }>(tenantPath(tenantId, "/backup/export"), { method: "POST", body: {} });
}

export async function getLicenseStatus(tenantId: string) {
  return apiRequest<{
    locked: boolean;
    status: string;
    reason: string | null;
    grace_ends_at: string | null;
  }>(tenantPath(tenantId, "/license/status"));
}

export interface SyncConflictRow {
  id?: number;
  record_id?: string;
  table_name?: string;
  field_name?: string;
  local_value?: unknown;
  remote_value?: unknown;
  is_locked_payment?: boolean;
  error_message?: string;
  resolved_by?: string;
  [key: string]: unknown;
}


// ── Biometric devices + Storage (Batch 3) ────────────────────────────

export async function getBiometricStatus(tenantId: string) {
  return apiRequest<{ pyzk_available: boolean; devices: BiometricDeviceRow[] }>(
    tenantPath(tenantId, "/attendance/biometric/status")
  );
}

export async function registerBiometricDevice(
  tenantId: string,
  body: { name: string; ip_address?: string; port?: number; device_type?: string }
) {
  return apiRequest<{ device_id: string; device: BiometricDeviceRow; pyzk_available: boolean }>(
    tenantPath(tenantId, "/attendance/biometric/devices"),
    { method: "POST", body }
  );
}

export async function testBiometricDevice(
  tenantId: string,
  deviceId: string,
  body: { ip?: string; port?: number } = {}
) {
  return apiRequest<{ ok: boolean; pyzk?: boolean; pyzk_available?: boolean; error?: string; message?: string }>(
    tenantPath(tenantId, `/attendance/biometric/devices/${deviceId}/test`),
    { method: "POST", body }
  );
}

export async function disableBiometricDevice(tenantId: string, deviceId: string) {
  return apiRequest<{ ok: boolean; is_active: boolean }>(
    tenantPath(tenantId, `/attendance/biometric/devices/${deviceId}/disable`),
    { method: "POST", body: {} }
  );
}

export async function linkDeviceUser(
  tenantId: string,
  studentId: string,
  deviceUserId: string
) {
  return apiRequest<{ ok: boolean }>(
    tenantPath(tenantId, "/attendance/biometric/link"),
    { method: "POST", body: { student_id: studentId, device_user_id: deviceUserId } }
  );
}

export async function linkDeviceUserBulk(
  tenantId: string,
  rows: { student_id?: string; roll?: string; device_user_id: string }[]
) {
  return apiRequest<{ linked: number; errors: unknown[] }>(
    tenantPath(tenantId, "/attendance/biometric/link-bulk"),
    { method: "POST", body: { rows } }
  );
}

export async function getStorageSettings(tenantId: string) {
  return apiRequest<{
    provider: string;
    configured: boolean;
    folder_id?: string | null;
    options: string[];
  }>(tenantPath(tenantId, "/settings/storage"));
}

export async function putStorageSettings(
  tenantId: string,
  body: {
    provider: string;
    folder_id?: string;
    access_token?: string;
    credentials_json?: string;
    root?: string;
  }
) {
  return apiRequest<{ ok: boolean; provider: string; configured: boolean }>(
    tenantPath(tenantId, "/settings/storage"),
    { method: "PUT", body }
  );
}

export async function testStorageProvider(tenantId: string) {
  return apiRequest<{ ok: boolean; error?: string; message?: string; remote_id?: string }>(
    tenantPath(tenantId, "/settings/storage/test"),
    { method: "POST", body: {} }
  );
}

export interface BiometricDeviceRow {
  id: string;
  name?: string;
  ip_address?: string;
  port?: number;
  is_active?: boolean;
  device_type?: string;
  [key: string]: unknown;
}


// ── Centre setup wizard (Batch 4) ───────────────────────────────────

export async function getSetupStatus(tenantId: string) {
  return apiRequest<{
    needs_wizard: boolean;
    batch_count: number;
    student_count: number;
    steps: {
      centre: boolean;
      first_batch: boolean;
      first_admission: boolean;
      done: boolean;
    };
  }>(tenantPath(tenantId, "/setup/status"));
}

export async function setupFirstBatch(
  tenantId: string,
  body: { days: string[]; hour: number; name?: string }
) {
  return apiRequest<{ batch_id: string; batch?: BatchRow }>(
    tenantPath(tenantId, "/setup/first-batch"),
    { method: "POST", body }
  );
}

/** Attempt silent refresh; returns true if we have a usable access token. */
export async function ensureSession(): Promise<boolean> {
  if (memoryAccessToken) return true;
  // API may still be booting after app relaunch — retry before forcing OTP.
  for (let attempt = 0; attempt < 8; attempt++) {
    const tokens = await refreshAccessToken();
    if (tokens && tokens.access_token) return true;
    // refreshAccessToken clears only on explicit auth failure (401/403), not network.
    // If we still have a stored refresh token, keep trying.
    let hasRt = false;
    if (typeof localStorage !== "undefined") {
      hasRt = !!localStorage.getItem(STORAGE_KEYS.refresh);
    }
    if (!hasRt && isElectron()) {
      try {
        hasRt = !!(await electronLoadRefresh());
      } catch {
        hasRt = false;
      }
    }
    if (!hasRt) return false;
    await new Promise((r) => setTimeout(r, 300 + attempt * 200));
  }
  return false;
}
