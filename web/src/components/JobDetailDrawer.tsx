"use client";

import DOMPurify from "dompurify";
import { Bot, Building2, ExternalLink, FileText, Gauge, Sparkles } from "lucide-react";
import { useMemo } from "react";

import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Drawer,
  DrawerClose,
  DrawerContent,
  DrawerDescription,
  DrawerFooter,
  DrawerHeader,
  DrawerTitle,
} from "@/components/ui/drawer";
import type { Job } from "@/lib/api";

type JobDetailDrawerProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  job: Job | null;
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

const statusLabel = (status: Job["status"]) => {
  if (status === "ready_for_ai") {
    return "ready for ai";
  }

  return status;
};

const scoreLabel = (score: number | null) => {
  if (score === null) {
    return "Nao analisado";
  }

  if (score >= 8) {
    return "Excelente match";
  }

  if (score >= 6) {
    return "Bom potencial";
  }

  return "Baixa aderencia";
};

const looksLikeHtml = (text: string) => /<\/?[a-z][\s\S]*>/i.test(text);

function DescriptionContent({ content }: { content: string }) {
  const trimmed = content.trim();
  const isHtml = looksLikeHtml(trimmed);

  const sanitizedHtml = useMemo(() => {
    if (!isHtml) {
      return "";
    }

    return DOMPurify.sanitize(trimmed);
  }, [isHtml, trimmed]);

  if (!trimmed) {
    return <p className="text-sm text-muted-foreground">Descricao nao disponivel.</p>;
  }

  if (isHtml) {
    return (
      <div
        className="space-y-2 text-sm leading-relaxed text-foreground [&_a]:text-primary [&_a]:underline [&_li]:ml-5 [&_li]:list-disc [&_p]:mb-3"
        dangerouslySetInnerHTML={{ __html: sanitizedHtml }}
      />
    );
  }

  return <p className="text-sm leading-relaxed whitespace-pre-wrap">{trimmed}</p>;
}

export function JobDetailDrawer({ open, onOpenChange, job }: JobDetailDrawerProps) {
  return (
    <Drawer open={open} onOpenChange={onOpenChange} direction="right">
      <DrawerContent className="w-full p-0 data-[vaul-drawer-direction=right]:w-full data-[vaul-drawer-direction=right]:sm:w-[40vw] data-[vaul-drawer-direction=right]:sm:min-w-[520px] data-[vaul-drawer-direction=right]:sm:max-w-[800px]">
        <div className="flex h-full max-h-screen flex-col">
          <DrawerHeader className="border-b border-border/70 bg-gradient-to-b from-muted/40 to-background">
            <DrawerTitle className="line-clamp-2 text-lg">{job?.title ?? "Detalhes da Vaga"}</DrawerTitle>
            <DrawerDescription className="line-clamp-1">
              {job?.company ?? "Selecione uma vaga para visualizar detalhes."}
            </DrawerDescription>
          </DrawerHeader>

          {job ? (
            <div className="flex-1 space-y-4 overflow-y-auto p-4">
              <Card className="border border-border/70 bg-card/90">
                <CardHeader className="pb-2">
                  <CardTitle className="flex items-center gap-2 text-sm">
                    <Building2 className="size-4 text-muted-foreground" />
                    Informacoes da Vaga
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-sm text-muted-foreground">Status</span>
                    <Badge variant={statusVariant(job.status)}>{statusLabel(job.status)}</Badge>
                  </div>

                  {job.url ? (
                    <a
                      href={job.url}
                      target="_blank"
                      rel="noreferrer"
                      className={buttonVariants({ variant: "outline" })}
                    >
                      <ExternalLink />
                      Abrir Link Original
                    </a>
                  ) : (
                    <p className="text-sm text-muted-foreground">Link original nao disponivel.</p>
                  )}
                </CardContent>
              </Card>

              <Card className="border border-border/70 bg-gradient-to-br from-muted/30 via-muted/10 to-background">
                <CardHeader className="pb-2">
                  <CardTitle className="flex items-center gap-2 text-sm">
                    <Sparkles className="size-4 text-amber-300" />
                    Resumo da Analise de IA
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="flex items-center justify-between gap-3 rounded-lg border border-border/70 bg-background/70 px-3 py-2">
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <Gauge className="size-4" />
                      Pontuacao IA
                    </div>
                    <Badge className={`h-9 px-3 text-sm ${scoreStyle(job.ai_score)}`} variant="outline">
                      {job.ai_score ?? "N/A"}
                    </Badge>
                  </div>

                  <p className="text-xs font-medium text-muted-foreground">{scoreLabel(job.ai_score)}</p>

                  {job.status === "analyzed" ? (
                    <div className="rounded-lg border border-border/70 bg-background/75 p-3 text-sm leading-relaxed shadow-sm">
                      {job.ai_summary?.trim() || "Resumo de IA indisponivel para esta vaga."}
                    </div>
                  ) : (
                    <div className="rounded-lg border border-dashed border-border/80 bg-background/50 p-3 text-sm text-muted-foreground">
                      Esta vaga ainda nao passou pela analise da IA. Clique em Run AI Analysis no topo para processar.
                    </div>
                  )}
                </CardContent>
              </Card>

              <Card className="border border-border/70 bg-card/90">
                <CardHeader className="pb-2">
                  <CardTitle className="flex items-center gap-2 text-sm">
                    <FileText className="size-4 text-muted-foreground" />
                    Descricao da Vaga
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <DescriptionContent content={job.description_raw} />
                </CardContent>
              </Card>
            </div>
          ) : null}

          <DrawerFooter className="border-t border-border/70 bg-background/95">
            <DrawerClose className={buttonVariants({ variant: "outline" })}>
              <Bot className="size-4" />
              Fechar
            </DrawerClose>
          </DrawerFooter>
        </div>
      </DrawerContent>
    </Drawer>
  );
}
