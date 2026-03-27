"use client";

import { useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { getJobs, type Job } from "@/lib/api";

type ViewMode = "table" | "cards";

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

export default function Home() {
  const [viewMode, setViewMode] = useState<ViewMode>("table");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadJobs = async () => {
      try {
        setLoading(true);
        const data = await getJobs();
        setJobs(data);
      } catch {
        setError("Nao foi possivel carregar as vagas do backend.");
      } finally {
        setLoading(false);
      }
    };

    void loadJobs();
  }, []);

  const jobsCount = useMemo(() => jobs.length, [jobs]);

  return (
    <main className="relative min-h-screen bg-background px-6 py-10 md:px-10">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(1200px_600px_at_20%_-10%,oklch(0.35_0_0/.22),transparent)]" />
      <section className="relative mx-auto flex w-full max-w-6xl flex-col gap-6">
        <Card className="border border-border/60 bg-card/80 backdrop-blur">
          <CardHeader className="gap-3">
            <CardTitle className="text-xl md:text-2xl">JobScouter Dashboard</CardTitle>
            <CardDescription>
              Vagas coletadas no backend FastAPI. Total listado: {jobsCount}
            </CardDescription>
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

        {loading ? (
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

        {!loading && !error && jobs.length === 0 ? (
          <Card>
            <CardContent className="py-8 text-muted-foreground">
              Nenhuma vaga encontrada.
            </CardContent>
          </Card>
        ) : null}

        {!loading && !error && jobs.length > 0 && viewMode === "table" ? (
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
                    <TableRow key={job.id}>
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
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        ) : null}

        {!loading && !error && jobs.length > 0 && viewMode === "cards" ? (
          <section className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {jobs.map((job) => (
              <Card key={job.id} className="border border-border/60">
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
      </section>
    </main>
  );
}
