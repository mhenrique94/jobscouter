import axios from "axios";

export type JobStatus = "pending" | "ready_for_ai" | "discarded" | "analyzed";
export type SyncSource = "all" | "remoteok" | "remotar";

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

const API_TIMEOUT_MS = 10_000;
const ANALYZE_JOB_TIMEOUT_MS = 90_000;
const API_BASE_PATH = process.env.NEXT_PUBLIC_API_BASE_PATH?.trim() || "/api/v1";

export const api = axios.create({
  baseURL: API_BASE_PATH,
  timeout: API_TIMEOUT_MS,
});

export async function getJobs(page = 1, size = 50): Promise<PaginatedJobsResponse> {
  const response = await api.get<JobsApiResponse>("/jobs", {
    params: { page, size },
  });

  if (Array.isArray(response.data)) {
    const items = response.data;
    return {
      items,
      total: items.length,
      page: 1,
      size: items.length || size,
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

export async function syncIngest(source: SyncSource = "all", limit = 20): Promise<BackgroundTaskAccepted> {
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

export async function analyzeJob(jobId: number): Promise<Job> {
  const response = await api.post<Job>(`/control/analyze/${jobId}`, null, {
    timeout: ANALYZE_JOB_TIMEOUT_MS,
  });
  return response.data;
}
