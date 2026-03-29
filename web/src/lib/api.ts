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
const API_BASE_PATH = "/api/v1";

export const api = axios.create({
  baseURL: API_BASE_PATH,
  timeout: API_TIMEOUT_MS,
});

export async function getJobs(limit = 50): Promise<Job[]> {
  const response = await api.get<Job[]>("/jobs", {
    params: { limit },
  });

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
