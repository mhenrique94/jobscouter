"use client";

import axios from "axios";
import Link from "next/link";
import { Loader2, RefreshCcw, ScrollText, Settings2 } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { JobDetailDrawer } from "@/components/JobDetailDrawer";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Drawer,
  DrawerClose,
  DrawerContent,
  DrawerFooter,
  DrawerHeader,
  DrawerTitle,
} from "@/components/ui/drawer";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/pagination";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { getJobs, getLogs, syncAnalyze, syncIngest, type Job, type JobsFilters } from "@/lib/api";

type ViewMode = "table" | "cards";
type PageToken = number | "ellipsis-left" | "ellipsis-right";
type DashboardTabKey = "ready" | "analyze" | "adjust" | "review" | "discarded" | "all";

type DashboardTabDefinition = {
  key: DashboardTabKey;
  label: string;
  summary: string;
  filters: JobsFilters;
};

const DEFAULT_PAGE_SIZE = 50;

function formatDate(dateStr: string) {
  return new Date(dateStr).toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
  });
}
const DEFAULT_TAB_KEY: DashboardTabKey = "ready";
const DASHBOARD_TABS: DashboardTabDefinition[] = [
  {
    key: "ready",
    label: "Prontas",
    summary: "Vagas analisadas com score 7-10 para decisão imediata.",
    filters: { status: ["analyzed"], min_score: 7 },
  },
  {
    key: "analyze",
    label: "Analisar",
    summary: "Vagas prontas para rodar a análise de IA.",
    filters: { status: ["ready_for_ai"] },
  },
  {
    key: "adjust",
    label: "Ajustar IA",
    summary: "Vagas analisadas com score 0-6 para recalibrar os critérios da IA.",
    filters: { status: ["analyzed"], max_score: 6 },
  },
  {
    key: "review",
    label: "Revisar",
    summary: "Vagas pendentes para revisar keywords e contexto de filtro.",
    filters: { status: ["pending"] },
  },
  {
    key: "discarded",
    label: "Descartadas",
    summary: "Vagas descartadas para auditoria pontual do funil.",
    filters: { status: ["discarded"] },
  },
  {
    key: "all",
    label: "Todas",
    summary: "Visão geral sem filtro de score, ocultando descartadas por padrão.",
    filters: { exclude_status: ["discarded"] },
  },
];
const DASHBOARD_TAB_KEYS = new Set<DashboardTabKey>(DASHBOARD_TABS.map((tab) => tab.key));

const getTabDefinition = (tabKey: DashboardTabKey) =>
  DASHBOARD_TABS.find((tab) => tab.key === tabKey) ?? DASHBOARD_TABS[0];

const buildPaginationItems = (page: number, totalPages: number): PageToken[] => {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, index) => index + 1);
  }

  const middlePages = [page - 1, page, page + 1].filter(
    (value) => value > 1 && value < totalPages
  );
  const items: PageToken[] = [1];

  if (middlePages.length > 0 && middlePages[0] > 2) {
    items.push("ellipsis-left");
  }

  items.push(...middlePages);

  if (middlePages.length > 0 && middlePages[middlePages.length - 1] < totalPages - 1) {
    items.push("ellipsis-right");
  }

  items.push(totalPages);
  return items;
};

const scoreStyle = (score: number | null) => {
  if (score === null) {
    return "bg-muted text-muted-foreground border-border";
  }

  if (score >= 8) {
    return "border-emerald-400/40 bg-emerald-500/15 text-emerald-300";
  }

  if (score >= 6) {
    return "border-amber-400/40 bg-amber-500/15 text-amber-300";
  }

  return "border-rose-400/40 bg-rose-500/15 text-rose-300";
};

const statusVariant = (status: Job["status"]) => {
  if (status === "analyzed") {
    return "default";
  }

  if (status === "discarded") {
    return "destructive";
  }

  return "secondary";
};

const getRequestErrorMessage = (error: unknown, fallback: string) => {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === "string" && detail.length > 0) {
      return detail;
    }
  }

  return fallback;
};

function HomeContent() {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const tabFromUrl = searchParams.get("tab");
  const currentTabKey = useMemo<DashboardTabKey>(() => {
    if (tabFromUrl && DASHBOARD_TAB_KEYS.has(tabFromUrl as DashboardTabKey)) {
      return tabFromUrl as DashboardTabKey;
    }

    return DEFAULT_TAB_KEY;
  }, [tabFromUrl]);
  const currentTab = useMemo(() => getTabDefinition(currentTabKey), [currentTabKey]);

  const pageFromUrl = searchParams.get("page");
  const currentPage = useMemo(() => {
    if (!pageFromUrl) {
      return 1;
    }

    const parsedPage = Number(pageFromUrl);
    if (!Number.isInteger(parsedPage) || parsedPage < 1) {
      return 1;
    }

    return parsedPage;
  }, [pageFromUrl]);

  const [viewMode, setViewMode] = useState<ViewMode>("table");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [totalJobs, setTotalJobs] = useState(0);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [selectedJob, setSelectedJob] = useState<Job | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [ingesting, setIngesting] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [logsOpen, setLogsOpen] = useState(false);
  const [logLines, setLogLines] = useState<string[]>([]);
  const [loadingLogs, setLoadingLogs] = useState(false);
  const [tabTotals, setTabTotals] = useState<Partial<Record<DashboardTabKey, number>>>({});
  const requestIdRef = useRef(0);
  const silentRefreshIdRef = useRef(0);
  const autoRefreshRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const totalPages = useMemo(
    () => Math.max(1, Math.ceil(totalJobs / Math.max(1, pageSize))),
    [totalJobs, pageSize]
  );

  const pageItems = useMemo(
    () => buildPaginationItems(currentPage, totalPages),
    [currentPage, totalPages]
  );

  const jobsRange = useMemo(() => {
    if (totalJobs === 0) {
      return { start: 0, end: 0 };
    }

    const start = (currentPage - 1) * pageSize + 1;
    const end = Math.min(totalJobs, currentPage * pageSize);
    return { start, end };
  }, [currentPage, pageSize, totalJobs]);

  const buildDashboardHref = (tabKey: DashboardTabKey, nextPage = 1) => {
    const params = new URLSearchParams(searchParams.toString());
    if (tabKey === DEFAULT_TAB_KEY) {
      params.delete("tab");
    } else {
      params.set("tab", tabKey);
    }

    if (nextPage <= 1) {
      params.delete("page");
    } else {
      params.set("page", String(nextPage));
    }

    const queryString = params.toString();
    return queryString ? `${pathname}?${queryString}` : pathname;
  };

  const navigateToPage = (nextPage: number) => {
    const safePage = Math.min(Math.max(nextPage, 1), totalPages);
    if (safePage === currentPage) {
      return;
    }
    router.push(buildDashboardHref(currentTabKey, safePage));
  };

  const selectTab = (tabKey: DashboardTabKey) => {
    if (tabKey === currentTabKey) {
      return;
    }

    router.push(buildDashboardHref(tabKey, 1));
  };

  const openJobDetails = (job: Job) => {
    setSelectedJob(job);
    setDrawerOpen(true);
  };

  const updateTabTotal = useCallback((tabKey: DashboardTabKey, total: number) => {
    setTabTotals((currentTotals) => {
      if (currentTotals[tabKey] === total) {
        return currentTotals;
      }

      return { ...currentTotals, [tabKey]: total };
    });
  }, []);

  const loadJobs = useCallback(async (page: number, tabKey: DashboardTabKey) => {
    const requestId = ++requestIdRef.current;
    const selectedTab = getTabDefinition(tabKey);
    try {
      setLoading(true);
      setError(null);
      const data = await getJobs({ ...selectedTab.filters, page, size: DEFAULT_PAGE_SIZE });
      if (requestId !== requestIdRef.current) {
        return;
      }

      setJobs(data.items);
      setTotalJobs(data.total);
      setPageSize(data.size);
      updateTabTotal(tabKey, data.total);
    } catch (requestError) {
      if (requestId !== requestIdRef.current) {
        return;
      }

      setError(getRequestErrorMessage(requestError, "Não foi possível carregar as vagas do backend."));
    } finally {
      if (requestId === requestIdRef.current) {
        setLoading(false);
      }
    }
  }, [updateTabTotal]);

  const loadTabTotal = useCallback(
    async (tabKey: DashboardTabKey) => {
      if (tabTotals[tabKey] !== undefined) {
        return;
      }

      const tab = getTabDefinition(tabKey);
      try {
        const data = await getJobs({ ...tab.filters, page: 1, size: 1 });
        updateTabTotal(tabKey, data.total);
      } catch {
        // Mantem a aba sem contador se a consulta falhar.
      }
    },
    [tabTotals, updateTabTotal]
  );

  useEffect(() => {
    void loadJobs(currentPage, currentTabKey);
  }, [currentPage, currentTabKey, loadJobs]);

  useEffect(() => {
    void loadTabTotal(currentTabKey);
  }, [currentTabKey, loadTabTotal]);

  const refreshSilently = useCallback(async (page: number, tabKey: DashboardTabKey) => {
    const requestId = ++silentRefreshIdRef.current;
    const selectedTab = getTabDefinition(tabKey);
    try {
      const data = await getJobs({ ...selectedTab.filters, page, size: DEFAULT_PAGE_SIZE });
      if (requestId !== silentRefreshIdRef.current) return;
      setJobs(data.items);
      setTotalJobs(data.total);
      setPageSize(data.size);
      setTabTotals({});
    } catch {
      // Silencioso — não exibe erro no auto-refresh.
    }
  }, []);

  useEffect(() => {
    autoRefreshRef.current = setInterval(() => {
      void refreshSilently(currentPage, currentTabKey);
    }, 60_000);
    return () => {
      if (autoRefreshRef.current) clearInterval(autoRefreshRef.current);
    };
  }, [currentPage, currentTabKey, refreshSilently]);

  const onSyncIngest = async () => {
    try {
      setIngesting(true);
      const response = await syncIngest();
      toast.success(response.detail || "Ingestão aceita em background.");
      setTabTotals({});
      await loadJobs(currentPage, currentTabKey);
    } catch (requestError) {
      toast.error(getRequestErrorMessage(requestError, "Falha ao iniciar sincronização de vagas."));
    } finally {
      setIngesting(false);
    }
  };

  const onSyncAnalyze = async () => {
    try {
      setAnalyzing(true);
      const response = await syncAnalyze();
      toast.success(response.detail || "Análise IA aceita em background.");
      setTabTotals({});
      await loadJobs(currentPage, currentTabKey);
    } catch (requestError) {
      toast.error(getRequestErrorMessage(requestError, "Falha ao iniciar análise IA."));
    } finally {
      setAnalyzing(false);
    }
  };

  const openLogs = async () => {
    setLogsOpen(true);
    setLoadingLogs(true);
    try {
      const data = await getLogs(300);
      setLogLines(data.lines);
    } catch {
      setLogLines(["Erro ao carregar logs."]);
    } finally {
      setLoadingLogs(false);
    }
  };

  const onJobUpdated = (updatedJob: Job) => {
    setSelectedJob(updatedJob);
    setTabTotals({});
    void loadJobs(currentPage, currentTabKey);
  };

  const jobsCount = useMemo(() => totalJobs, [totalJobs]);
  const showInitialLoading = loading && jobs.length === 0;
  const showTableView = !error && viewMode === "table" && (jobs.length > 0 || totalJobs > 0 || loading);
  const showCardsView = !loading && !error && jobs.length > 0 && viewMode === "cards";

  const tabCountLabel = useCallback(
    (tabKey: DashboardTabKey) => {
      if (tabKey === currentTabKey) {
        if (loading && tabTotals[tabKey] === undefined) {
          return "...";
        }

        return String(totalJobs);
      }

      const cachedTotal = tabTotals[tabKey];
      return cachedTotal === undefined ? "..." : String(cachedTotal);
    },
    [currentTabKey, loading, tabTotals, totalJobs]
  );

  useEffect(() => {
    if (loading || totalJobs === 0 || currentPage <= totalPages) {
      return;
    }

    const params = new URLSearchParams(searchParams.toString());
    if (currentTabKey === DEFAULT_TAB_KEY) {
      params.delete("tab");
    } else {
      params.set("tab", currentTabKey);
    }

    if (totalPages <= 1) {
      params.delete("page");
    } else {
      params.set("page", String(totalPages));
    }

    const queryString = params.toString();
    router.replace(queryString ? `${pathname}?${queryString}` : pathname);
  }, [currentPage, currentTabKey, loading, pathname, router, searchParams, totalJobs, totalPages]);

  return (
    <main className="relative min-h-screen bg-background px-6 py-10 md:px-10">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(1200px_600px_at_20%_-10%,oklch(0.35_0_0/.22),transparent)]" />
      <section className="relative mx-auto flex w-full max-w-6xl flex-col gap-6">
        <Card className="border border-border/60 bg-card/80 backdrop-blur">
          <CardHeader className="gap-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <CardTitle className="text-xl md:text-2xl">JobScouter Dashboard</CardTitle>
                <CardDescription>
                  {currentTab.summary} Total na aba: {jobsCount}
                </CardDescription>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Link href="/settings" className={buttonVariants({ variant: "outline" })}>
                  <Settings2 />
                  Configurações
                </Link>
                <Button type="button" variant="outline" onClick={() => void openLogs()}>
                  <ScrollText />
                  Ver Logs
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => void loadJobs(currentPage, currentTabKey)}
                  disabled={loading}
                >
                  <RefreshCcw className={loading ? "animate-spin" : ""} />
                  Atualizar Lista
                </Button>
                <Button type="button" variant="secondary" onClick={onSyncIngest} disabled={ingesting}>
                  {ingesting ? <Loader2 className="animate-spin" /> : null}
                  Sincronizar Vagas
                </Button>
                <Button type="button" onClick={onSyncAnalyze} disabled={analyzing}>
                  {analyzing ? <Loader2 className="animate-spin" /> : null}
                  Rodar Analise IA
                </Button>
              </div>
            </div>

            <div className="flex flex-wrap gap-2">
              {DASHBOARD_TABS.map((tab) => (
                <Button
                  key={tab.key}
                  variant={tab.key === currentTabKey ? "default" : "outline"}
                  onClick={() => selectTab(tab.key)}
                  onMouseEnter={() => void loadTabTotal(tab.key)}
                  onFocus={() => void loadTabTotal(tab.key)}
                  type="button"
                >
                  {tab.label} ({tabCountLabel(tab.key)})
                </Button>
              ))}
            </div>

            <div className="flex flex-wrap gap-2">
              <Button
                variant={viewMode === "table" ? "default" : "outline"}
                onClick={() => setViewMode("table")}
                type="button"
              >
                Tabela
              </Button>
              <Button
                variant={viewMode === "cards" ? "default" : "outline"}
                onClick={() => setViewMode("cards")}
                type="button"
              >
                Cards
              </Button>
            </div>
          </CardHeader>
        </Card>

        {showInitialLoading ? (
          <Card>
            <CardContent className="py-8 text-muted-foreground">
              Carregando vagas...
            </CardContent>
          </Card>
        ) : null}

        {error ? (
          <Card>
            <CardContent className="py-8 text-destructive">{error}</CardContent>
          </Card>
        ) : null}

        {!loading && !error && jobs.length === 0 && totalJobs === 0 ? (
          <Card>
            <CardContent className="py-8 text-muted-foreground">
              Nenhuma vaga encontrada.
            </CardContent>
          </Card>
        ) : null}

        {showTableView ? (
          <Card>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Titulo</TableHead>
                    <TableHead>Empresa</TableHead>
                    <TableHead>Score IA</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Inclusão</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {jobs.map((job) => (
                    <TableRow
                      key={job.id}
                      className="cursor-pointer hover:bg-muted"
                      onClick={() => openJobDetails(job)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          openJobDetails(job);
                        }
                      }}
                      tabIndex={0}
                    >
                      <TableCell className="font-medium">{job.title}</TableCell>
                      <TableCell>{job.company}</TableCell>
                      <TableCell>
                        <Badge className={scoreStyle(job.ai_score)} variant="outline">
                          {job.ai_score ?? "N/A"}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Badge variant={statusVariant(job.status)}>{job.status}</Badge>
                      </TableCell>
                      <TableCell className="text-muted-foreground">{formatDate(job.created_at)}</TableCell>
                    </TableRow>
                  ))}
                  {!loading && jobs.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={5} className="py-8 text-center text-muted-foreground">
                        Nenhuma vaga nesta página.
                      </TableCell>
                    </TableRow>
                  ) : null}
                </TableBody>
              </Table>

              <div className="mt-6 flex flex-col items-center gap-3 border-t border-border/60 pt-4">
                <div className="text-sm text-muted-foreground">
                  Mostrando {jobsRange.start}-{jobsRange.end} de {totalJobs} vagas em {currentTab.label}.
                  {loading ? (
                    <span className="ml-2 inline-flex items-center gap-1">
                      <Loader2 className="size-4 animate-spin" />
                      Atualizando página...
                    </span>
                  ) : null}
                </div>

                <Pagination>
                  <PaginationContent>
                    <PaginationItem>
                      <PaginationPrevious
                        href={buildDashboardHref(currentTabKey, currentPage - 1)}
                        className={currentPage <= 1 ? "pointer-events-none opacity-50" : undefined}
                        onClick={(event) => {
                          event.preventDefault();
                          navigateToPage(currentPage - 1);
                        }}
                      />
                    </PaginationItem>

                    {pageItems.map((item) => {
                      if (item === "ellipsis-left" || item === "ellipsis-right") {
                        return (
                          <PaginationItem key={item}>
                            <PaginationEllipsis />
                          </PaginationItem>
                        );
                      }

                      return (
                        <PaginationItem key={item}>
                          <PaginationLink
                            href={buildDashboardHref(currentTabKey, item)}
                            isActive={item === currentPage}
                            onClick={(event) => {
                              event.preventDefault();
                              navigateToPage(item);
                            }}
                          >
                            {item}
                          </PaginationLink>
                        </PaginationItem>
                      );
                    })}

                    <PaginationItem>
                      <PaginationNext
                        href={buildDashboardHref(currentTabKey, currentPage + 1)}
                        className={
                          currentPage >= totalPages ? "pointer-events-none opacity-50" : undefined
                        }
                        onClick={(event) => {
                          event.preventDefault();
                          navigateToPage(currentPage + 1);
                        }}
                      />
                    </PaginationItem>
                  </PaginationContent>
                </Pagination>
              </div>
            </CardContent>
          </Card>
        ) : null}

        {showCardsView ? (
          <div className="flex flex-col gap-4">
            <section className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
              {jobs.map((job) => (
                <Card
                  key={job.id}
                  className="cursor-pointer border border-border/60 transition-all hover:scale-[1.01] hover:shadow-lg"
                  onClick={() => openJobDetails(job)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      openJobDetails(job);
                    }
                  }}
                  tabIndex={0}
                >
                  <CardHeader className="gap-2">
                    <CardTitle className="line-clamp-2 text-base">{job.title}</CardTitle>
                    <CardDescription>{job.company}</CardDescription>
                  </CardHeader>
                  <CardContent className="flex items-center justify-between gap-3">
                    <Badge className={scoreStyle(job.ai_score)} variant="outline">
                      Score: {job.ai_score ?? "N/A"}
                    </Badge>
                    <Badge variant={statusVariant(job.status)}>{job.status}</Badge>
                    <span className="text-xs text-muted-foreground">{formatDate(job.created_at)}</span>
                  </CardContent>
                </Card>
              ))}
            </section>

            <div className="flex flex-col items-center gap-3 border-t border-border/60 pt-4">
              <div className="text-sm text-muted-foreground">
                Mostrando {jobsRange.start}-{jobsRange.end} de {totalJobs} vagas em {currentTab.label}.
              </div>

              <Pagination>
                <PaginationContent>
                  <PaginationItem>
                    <PaginationPrevious
                      href={buildDashboardHref(currentTabKey, currentPage - 1)}
                      className={currentPage <= 1 ? "pointer-events-none opacity-50" : undefined}
                      onClick={(event) => {
                        event.preventDefault();
                        navigateToPage(currentPage - 1);
                      }}
                    />
                  </PaginationItem>

                  {pageItems.map((item) => {
                    if (item === "ellipsis-left" || item === "ellipsis-right") {
                      return (
                        <PaginationItem key={item}>
                          <PaginationEllipsis />
                        </PaginationItem>
                      );
                    }

                    return (
                      <PaginationItem key={item}>
                        <PaginationLink
                          href={buildDashboardHref(currentTabKey, item)}
                          isActive={item === currentPage}
                          onClick={(event) => {
                            event.preventDefault();
                            navigateToPage(item);
                          }}
                        >
                          {item}
                        </PaginationLink>
                      </PaginationItem>
                    );
                  })}

                  <PaginationItem>
                    <PaginationNext
                      href={buildDashboardHref(currentTabKey, currentPage + 1)}
                      className={
                        currentPage >= totalPages ? "pointer-events-none opacity-50" : undefined
                      }
                      onClick={(event) => {
                        event.preventDefault();
                        navigateToPage(currentPage + 1);
                      }}
                    />
                  </PaginationItem>
                </PaginationContent>
              </Pagination>
            </div>
          </div>
        ) : null}

        <Drawer open={logsOpen} onOpenChange={setLogsOpen} direction="bottom">
          <DrawerContent className="max-h-[75vh]">
            <DrawerHeader className="flex items-center justify-between">
              <DrawerTitle>Logs da aplicação</DrawerTitle>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => void openLogs()}
                disabled={loadingLogs}
              >
                {loadingLogs ? <Loader2 className="animate-spin" /> : <RefreshCcw />}
                Atualizar
              </Button>
            </DrawerHeader>
            <div className="overflow-y-auto px-4 pb-2">
              {loadingLogs ? (
                <p className="text-sm text-muted-foreground">Carregando logs...</p>
              ) : logLines.length === 0 ? (
                <p className="text-sm text-muted-foreground">Nenhum log disponível ainda.</p>
              ) : (
                <pre className="whitespace-pre-wrap break-all font-mono text-xs leading-5 text-foreground">
                  {logLines.join("\n")}
                </pre>
              )}
            </div>
            <DrawerFooter>
              <DrawerClose asChild>
                <Button variant="outline">Fechar</Button>
              </DrawerClose>
            </DrawerFooter>
          </DrawerContent>
        </Drawer>

        <JobDetailDrawer
          open={drawerOpen}
          onOpenChange={setDrawerOpen}
          job={selectedJob}
          onJobUpdated={onJobUpdated}
        />
      </section>
    </main>
  );
}

export default function Home() {
  return (
    <Suspense
      fallback={
        <main className="relative min-h-screen bg-background px-6 py-10 md:px-10">
          <section className="relative mx-auto flex w-full max-w-6xl flex-col gap-6">
            <Card>
              <CardContent className="py-8 text-muted-foreground">Carregando vagas...</CardContent>
            </Card>
          </section>
        </main>
      }
    >
      <HomeContent />
    </Suspense>
  );
}
