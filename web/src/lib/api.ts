import axios from "axios";

export type JobStatus = "pending" | "ready_for_ai" | "discarded" | "analyzed";

export interface Job {
  id: number;
  title: string;
  company: string;
  status: JobStatus;
  ai_score: number | null;
}

const API_TIMEOUT_MS = 10_000;

export const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_BASE_PATH ?? "",
  timeout: API_TIMEOUT_MS,
});

export async function getJobs(limit = 50): Promise<Job[]> {
  const response = await api.get<Job[]>("/jobs", {
    params: { limit },
  });

  return response.data;
}
