"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronUp, Database, Sparkles, Trash2, Terminal } from "lucide-react";
import { cn } from "@/lib/utils";
import { useTaskStream, type LogEntry, type TaskState, type TaskType } from "@/hooks/useTaskStream";

// ─── Log level ────────────────────────────────────────────────────────────────

type LogLevel = "error" | "warning" | "info" | "debug" | "default";

function detectLevel(line: string): LogLevel {
  const u = line.toUpperCase();
  if (u.includes(" ERROR") || u.includes("EXCEPTION") || u.includes("FALHA")) return "error";
  if (u.includes(" WARNING") || u.includes(" WARN")) return "warning";
  if (u.includes(" INFO")) return "info";
  if (u.includes(" DEBUG")) return "debug";
  return "default";
}

const LEVEL_CLASS: Record<LogLevel, string> = {
  error: "text-rose-400",
  warning: "text-amber-400",
  info: "text-zinc-500",
  debug: "text-zinc-700",
  default: "text-zinc-400",
};

// ─── Task metadata ─────────────────────────────────────────────────────────────

const TASK_ICON: Record<TaskType, React.ReactNode> = {
  ingest: <Database className="size-3 shrink-0" />,
  analyze: <Sparkles className="size-3 shrink-0" />,
  cleanup: <Trash2 className="size-3 shrink-0" />,
};

const TASK_LABEL: Record<TaskType, string> = {
  ingest: "ingestão",
  analyze: "análise ia",
  cleanup: "limpeza",
};

const STATUS_CLASS: Record<TaskState["status"], string> = {
  running: "border-blue-500/30 bg-blue-500/10 text-blue-400",
  done: "border-emerald-500/30 bg-emerald-500/10 text-emerald-400",
  error: "border-rose-500/30 bg-rose-500/10 text-rose-400",
};

// ─── Sub-components ────────────────────────────────────────────────────────────

function ConnectionDot({ connected }: { connected: boolean }) {
  return (
    <span className="flex items-center gap-1.5">
      <span
        className={cn(
          "size-1.5 rounded-full transition-colors duration-700",
          connected
            ? "bg-emerald-400 shadow-[0_0_5px_1px_theme(colors.emerald.400/40%)]"
            : "bg-zinc-700",
        )}
      />
      <span className="font-mono text-[10px] text-zinc-600 tabular-nums">
        {connected ? "online" : "offline"}
      </span>
    </span>
  );
}

function TaskChip({ task }: { task: TaskState }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded border px-1.5 py-px font-mono text-[10px] font-medium",
        STATUS_CLASS[task.status],
      )}
    >
      {TASK_ICON[task.type]}
      {TASK_LABEL[task.type]}
      {task.status === "running" && (
        <span className="size-1 animate-pulse rounded-full bg-current" />
      )}
    </span>
  );
}

// ─── ActivityPanel ─────────────────────────────────────────────────────────────

export function ActivityPanel() {
  const { logs, tasks, connected } = useTaskStream();
  const [expanded, setExpanded] = useState(false);
  const [autoScroll, setAutoScroll] = useState(true);

  const logContainerRef = useRef<HTMLDivElement>(null);
  const logEndRef = useRef<HTMLDivElement>(null);

  const runningTasks = tasks.filter((t) => t.status === "running");

  // Auto-scroll quando chegam novas linhas
  useEffect(() => {
    if (autoScroll && expanded) {
      logEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs, autoScroll, expanded]);

  // Desativa auto-scroll se o usuário rolou para cima
  const handleScroll = () => {
    const el = logContainerRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop <= el.clientHeight + 40;
    setAutoScroll(atBottom);
  };

  const scrollToBottom = () => {
    setAutoScroll(true);
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  return (
    <div
      className={cn(
        "fixed bottom-0 left-0 right-0 z-50 flex flex-col",
        "border-t border-zinc-700 bg-zinc-900 backdrop-blur-md",
        "transition-[height] duration-300 ease-in-out will-change-[height]",
        expanded ? "h-72" : "h-8",
      )}
    >
      {/* ── Barra de status (sempre visível, inteira clicável) ── */}
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        aria-label={expanded ? "Recolher painel de logs" : "Expandir painel de logs"}
        className="flex h-8 w-full shrink-0 cursor-pointer items-center gap-2.5 overflow-hidden px-3 transition-colors hover:bg-zinc-800/60"
      >
        <ConnectionDot connected={connected} />

        <span className="h-3 w-px shrink-0 bg-zinc-700" />

        <span className="hidden items-center gap-1.5 text-zinc-400 sm:flex">
          <Terminal className="size-3" />
          <span className="font-mono text-[10px]">output</span>
        </span>

        {runningTasks.length > 0 && (
          <>
            <span className="hidden h-3 w-px shrink-0 bg-zinc-700 sm:block" />
            <div className="flex min-w-0 items-center gap-1.5 overflow-hidden">
              {runningTasks.slice(0, 2).map((task) => (
                <TaskChip key={task.id} task={task} />
              ))}
              {runningTasks.length > 2 && (
                <span className="font-mono text-[10px] text-zinc-500">
                  +{runningTasks.length - 2}
                </span>
              )}
            </div>
          </>
        )}

        <span className="ml-auto hidden shrink-0 font-mono text-[10px] tabular-nums text-zinc-500 sm:inline">
          {logs.length > 0 ? `${logs.length} linhas` : ""}
        </span>

        <span className="shrink-0 text-zinc-400">
          {expanded ? <ChevronDown className="size-3" /> : <ChevronUp className="size-3" />}
        </span>
      </button>

      {/* ── Conteúdo expandido ── */}
      <div
        className={cn(
          "relative flex min-h-0 flex-1 flex-col overflow-hidden transition-opacity duration-200",
          expanded ? "opacity-100" : "pointer-events-none opacity-0",
        )}
      >
        {/* Status das tasks em execução */}
        {tasks.length > 0 && (
          <div className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-1 border-b border-zinc-700/60 px-3 py-1.5">
            {tasks.map((task) => (
              <div key={task.id} className="flex items-center gap-2">
                <TaskChip task={task} />
                {task.detail && (
                  <span className="font-mono text-[10px] text-zinc-600">{task.detail}</span>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Área de logs */}
        <div
          ref={logContainerRef}
          onScroll={handleScroll}
          className="flex-1 overflow-y-auto px-3 py-2"
        >
          {logs.length === 0 ? (
            <p className="font-mono text-[11px] italic text-zinc-700">aguardando atividade...</p>
          ) : (
            logs.map(({ id, line }: LogEntry) => (
              <div
                key={id}
                className={cn("font-mono text-[11px] leading-5", LEVEL_CLASS[detectLevel(line)])}
              >
                {line}
              </div>
            ))
          )}
          <div ref={logEndRef} />
        </div>

        {/* Botão "ir para o fim" quando auto-scroll está desativado */}
        {!autoScroll && expanded && (
          <button
            onClick={scrollToBottom}
            type="button"
            className={cn(
              "absolute bottom-3 right-4 rounded border border-zinc-700 bg-zinc-900/90",
              "px-2 py-1 font-mono text-[10px] text-zinc-400 shadow-lg",
              "transition-colors hover:border-zinc-600 hover:text-zinc-200",
            )}
          >
            ↓ ir para o fim
          </button>
        )}
      </div>
    </div>
  );
}
