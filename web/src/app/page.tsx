"use client";

import axios from "axios";
import Link from "next/link";
import { Loader2, RefreshCcw, Settings2 } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { JobDetailDrawer } from "@/components/JobDetailDrawer";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
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
import { getJobs, syncAnalyze, syncIngest, type Job } from "@/lib/api";

type ViewMode = "table" | "cards";
type PageToken = number | "ellipsis-left" | "ellipsis-right";

const DEFAULT_PAGE_SIZE = 50;

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
  const requestIdRef = useRef(0);

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

  const buildPageHref = (nextPage: number) => {
    const params = new URLSearchParams(searchParams.toString());
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
    router.push(buildPageHref(safePage));
  };

  const openJobDetails = (job: Job) => {
    setSelectedJob(job);
    setDrawerOpen(true);
  };

  const loadJobs = useCallback(async (page: number) => {
    const requestId = ++requestIdRef.current;
    try {
      setLoading(true);
      setError(null);
      const data = await getJobs(page, DEFAULT_PAGE_SIZE);
      if (requestId !== requestIdRef.current) {
        return;
      }

      setJobs(data.items);
      setTotalJobs(data.total);
      setPageSize(data.size);
    } catch (requestError) {
      if (requestId !== requestIdRef.current) {
        return;
      }

      setError(getRequestErrorMessage(requestError, "Nao foi possivel carregar as vagas do backend."));
    } finally {
      if (requestId === requestIdRef.current) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void loadJobs(currentPage);
  }, [currentPage, loadJobs]);

  const onSyncIngest = async () => {
    try {
      setIngesting(true);
      const response = await syncIngest();
      toast.success(response.detail || "Ingestao aceita em background.");
      await loadJobs(currentPage);
    } catch (requestError) {
      toast.error(getRequestErrorMessage(requestError, "Falha ao iniciar sincronizacao de vagas."));
    } finally {
      setIngesting(false);
    }
  };

  const onSyncAnalyze = async () => {
    try {
      setAnalyzing(true);
      const response = await syncAnalyze();
      toast.success(response.detail || "Analise IA aceita em background.");
      await loadJobs(currentPage);
    } catch (requestError) {
      toast.error(getRequestErrorMessage(requestError, "Falha ao iniciar analise IA."));
    } finally {
      setAnalyzing(false);
    }
  };

  const onJobUpdated = (updatedJob: Job) => {
    setJobs((currentJobs) =>
      currentJobs.map((job) => {
        if (job.id === updatedJob.id) {
          return updatedJob;
        }
        return job;
      })
    );

    setSelectedJob((currentJob) => {
      if (!currentJob || currentJob.id !== updatedJob.id) {
        return currentJob;
      }
      return updatedJob;
    });
  };

  const jobsCount = useMemo(() => totalJobs, [totalJobs]);
  const showInitialLoading = loading && jobs.length === 0;
  const showTableView = !error && viewMode === "table" && (jobs.length > 0 || totalJobs > 0 || loading);
  const showCardsView = !loading && !error && jobs.length > 0 && viewMode === "cards";

  useEffect(() => {
    if (loading || totalJobs === 0 || currentPage <= totalPages) {
      return;
    }

    const params = new URLSearchParams(searchParams.toString());
    if (totalPages <= 1) {
      params.delete("page");
    } else {
      params.set("page", String(totalPages));
    }

    const queryString = params.toString();
    router.replace(queryString ? `${pathname}?${queryString}` : pathname);
  }, [currentPage, loading, pathname, router, searchParams, totalJobs, totalPages]);

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
                  Vagas coletadas no backend FastAPI. Total listado: {jobsCount}
                </CardDescription>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Link href="/settings" className={buttonVariants({ variant: "outline" })}>
                  <Settings2 />
                  Configuracoes
                </Link>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => void loadJobs(currentPage)}
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
                    </TableRow>
                  ))}
                  {!loading && jobs.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={4} className="py-8 text-center text-muted-foreground">
                        Nenhuma vaga nesta pagina.
                      </TableCell>
                    </TableRow>
                  ) : null}
                </TableBody>
              </Table>

              <div className="mt-6 flex flex-col items-center gap-3 border-t border-border/60 pt-4">
                <div className="text-sm text-muted-foreground">
                  Mostrando {jobsRange.start}-{jobsRange.end} de {totalJobs} vagas.
                  {loading ? (
                    <span className="ml-2 inline-flex items-center gap-1">
                      <Loader2 className="size-4 animate-spin" />
                      Atualizando pagina...
                    </span>
                  ) : null}
                </div>

                <Pagination>
                  <PaginationContent>
                    <PaginationItem>
                      <PaginationPrevious
                        href={buildPageHref(currentPage - 1)}
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
                            href={buildPageHref(item)}
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
                        href={buildPageHref(currentPage + 1)}
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
                </CardContent>
              </Card>
            ))}
          </section>
        ) : null}

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
