"use client";

import { useEffect, useRef, useState } from "react";

export type TaskType = "ingest" | "analyze" | "cleanup";
export type TaskStatus = "running" | "done" | "error";

export interface TaskState {
  id: string;
  type: TaskType;
  status: TaskStatus;
  detail: string;
}

const MAX_LOG_LINES = 500;
const API_BASE_PATH = process.env.NEXT_PUBLIC_API_BASE_PATH?.trim() || "/api/v1";
const STREAM_URL = `${API_BASE_PATH}/control/stream`;

export function useTaskStream() {
  const [logs, setLogs] = useState<string[]>([]);
  const [tasks, setTasks] = useState<TaskState[]>([]);
  const [connected, setConnected] = useState(false);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    const es = new EventSource(STREAM_URL);
    esRef.current = es;

    es.addEventListener("log", (e) => {
      try {
        const { line } = JSON.parse((e as MessageEvent).data) as { line: string };
        setLogs((prev) => {
          const next = [...prev, line];
          return next.length > MAX_LOG_LINES ? next.slice(next.length - MAX_LOG_LINES) : next;
        });
      } catch {
        // ignora linha malformada
      }
    });

    es.addEventListener("tasks", (e) => {
      try {
        const data = JSON.parse((e as MessageEvent).data) as TaskState[];
        setTasks(data);
      } catch {
        // ignora snapshot malformado
      }
    });

    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);

    return () => {
      es.close();
    };
  }, []);

  return { logs, tasks, connected };
}
