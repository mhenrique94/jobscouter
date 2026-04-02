import axios from "axios";

export type JobStatus = "pending" | "ready_for_ai" | "discarded" | "analyzed";
export type ManualJobStatus = "ready_for_ai" | "discarded";
export type SyncSource = "all" | "remoteok" | "remotar";

export interface JobsFilters {
  status?: JobStatus[];
  exclude_status?: JobStatus[];
  min_score?: number;
  max_score?: number;
  page?: number;
  size?: number;
}

export interface Job {
  id: number;
  title: string;
  company: string;
  url: string;
  description_raw: string;
  status: JobStatus;
  ai_score: number | null;
  ai_summary: string | null;
  ai_analysis_at: string | null;
  created_at: string;
}

export interface PaginatedJobsResponse {
  items: Job[];
  total: number;
  page: number;
  size: number;
}

type JobsApiResponse = PaginatedJobsResponse | Job[];

export interface FilterConfig {
  search_terms: string[];
  include_keywords: string[];
  exclude_keywords: string[];
}

export interface FilterConfigPatchPayload {
  search_terms?: string[];
  include_keywords?: string[];
  exclude_keywords?: string[];
}

export interface BackgroundTaskAccepted {
  detail: string;
}

export interface LogsResponse {
  lines: string[];
}

const API_TIMEOUT_MS = 10_000;
const ANALYZE_JOB_TIMEOUT_MS = 90_000;
const API_BASE_PATH = process.env.NEXT_PUBLIC_API_BASE_PATH?.trim() || "/api/v1";

export const api = axios.create({
  baseURL: API_BASE_PATH,
  timeout: API_TIMEOUT_MS,
});

const buildJobsSearchParams = (filters: JobsFilters = {}) => {
  const params = new URLSearchParams();

  for (const status of filters.status ?? []) {
    params.append("status", status);
  }

  for (const status of filters.exclude_status ?? []) {
    params.append("exclude_status", status);
  }

  if (filters.min_score !== undefined) {
    params.set("min_score", String(filters.min_score));
  }

  if (filters.max_score !== undefined) {
    params.set("max_score", String(filters.max_score));
  }

  params.set("page", String(filters.page ?? 1));
  params.set("size", String(filters.size ?? 50));

  return params;
};

export async function getJobs(filters: JobsFilters = {}): Promise<PaginatedJobsResponse> {
  const response = await api.get<JobsApiResponse>("/jobs", {
    params: buildJobsSearchParams(filters),
  });

  if (Array.isArray(response.data)) {
    const items = response.data;
    return {
      items,
      total: items.length,
      page: 1,
      size: items.length || filters.size || 50,
    };
  }

  return response.data;
}

export async function getConfig(): Promise<FilterConfig> {
  const response = await api.get<FilterConfig>("/config");
  return response.data;
}

export async function patchConfig(payload: FilterConfigPatchPayload): Promise<FilterConfig> {
  const response = await api.patch<FilterConfig>("/config", payload);
  return response.data;
}

export async function syncIngest(source: SyncSource = "all", limit = 100): Promise<BackgroundTaskAccepted> {
  const response = await api.post<BackgroundTaskAccepted>("/control/sync/ingest", null, {
    params: { source, limit },
  });
  return response.data;
}

export async function syncAnalyze(limit?: number): Promise<BackgroundTaskAccepted> {
  const response = await api.post<BackgroundTaskAccepted>("/control/sync/analyze", null, {
    params: limit === undefined ? undefined : { limit },
  });
  return response.data;
}

export async function getLogs(lines = 200): Promise<LogsResponse> {
  const response = await api.get<LogsResponse>("/control/logs", { params: { lines } });
  return response.data;
}

export async function analyzeJob(jobId: number): Promise<Job> {
  const response = await api.post<Job>(`/control/analyze/${jobId}`, null, {
    timeout: ANALYZE_JOB_TIMEOUT_MS,
  });
  return response.data;
}

export async function updateJobStatus(jobId: number, status: ManualJobStatus): Promise<Job> {
  const response = await api.patch<Job>(`/control/jobs/${jobId}/status`, { status });
  return response.data;
}
