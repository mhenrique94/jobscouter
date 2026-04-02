"use client";

import axios from "axios";
import { Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import {
  cleanupAssertiveness,
  getConfig,
  patchConfig,
  syncAnalyze,
  syncIngest,
  type FilterConfig,
} from "@/lib/api";

function listToLines(values: string[]): string {
  return values.join("\n");
}

function linesToList(value: string): string[] {
  return value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}

function getRequestErrorMessage(error: unknown, fallback: string): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === "string" && detail.length > 0) {
      return detail;
    }
  }

  return fallback;
}

export default function SettingsPage() {
  const router = useRouter();
  const [config, setConfig] = useState<FilterConfig | null>(null);
  const [searchTerms, setSearchTerms] = useState("");
  const [includeKeywords, setIncludeKeywords] = useState("");
  const [excludeKeywords, setExcludeKeywords] = useState("");

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [ingesting, setIngesting] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [cleaningUp, setCleaningUp] = useState(false);

  useEffect(() => {
    const loadConfig = async () => {
      try {
        setLoading(true);
        const data = await getConfig();
        setConfig(data);
        setSearchTerms(listToLines(data.search_terms));
        setIncludeKeywords(listToLines(data.include_keywords));
        setExcludeKeywords(listToLines(data.exclude_keywords));
      } catch (error) {
        toast.error(getRequestErrorMessage(error, "Não foi possível carregar as configurações."));
      } finally {
        setLoading(false);
      }
    };

    void loadConfig();
  }, []);

  const hasLoadedConfig = useMemo(() => config !== null, [config]);

  const onSave = async () => {
    try {
      setSaving(true);
      const payload = {
        search_terms: linesToList(searchTerms),
        include_keywords: linesToList(includeKeywords),
        exclude_keywords: linesToList(excludeKeywords),
      };
      const updated = await patchConfig(payload);
      setConfig(updated);
      setSearchTerms(listToLines(updated.search_terms));
      setIncludeKeywords(listToLines(updated.include_keywords));
      setExcludeKeywords(listToLines(updated.exclude_keywords));
      toast.success("Configurações salvas com sucesso.");
    } catch (error) {
      toast.error(getRequestErrorMessage(error, "Falha ao salvar configurações."));
    } finally {
      setSaving(false);
    }
  };

  const onSyncIngest = async () => {
    try {
      setIngesting(true);
      const response = await syncIngest();
      toast.success(response.detail || "Ingestão aceita e iniciada em background.");
    } catch (error) {
      toast.error(getRequestErrorMessage(error, "Falha ao iniciar ingestão."));
    } finally {
      setIngesting(false);
    }
  };

  const onSyncAnalyze = async () => {
    try {
      setAnalyzing(true);
      const response = await syncAnalyze();
      toast.success(response.detail || "Análise IA aceita e iniciada em background.");
    } catch (error) {
      toast.error(getRequestErrorMessage(error, "Falha ao iniciar análise IA."));
    } finally {
      setAnalyzing(false);
    }
  };

  const onCleanupAssertiveness = async () => {
    try {
      setCleaningUp(true);
      const response = await cleanupAssertiveness();
      toast.success(response.detail || "Limpeza iniciada em background.");
    } catch (error) {
      toast.error(getRequestErrorMessage(error, "Falha ao iniciar limpeza de assertividade."));
    } finally {
      setCleaningUp(false);
    }
  };

  return (
    <main className="relative min-h-screen bg-background px-6 py-10 md:px-10">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(1200px_600px_at_20%_-10%,oklch(0.35_0_0/.22),transparent)]" />
      <section className="relative mx-auto flex w-full max-w-4xl flex-col gap-6">
        <Card className="border border-border/60 bg-card/80 backdrop-blur">
          <CardHeader className="gap-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <CardTitle className="text-xl md:text-2xl">Configurações de Filtros</CardTitle>
                <CardDescription>
                  Ajuste search terms e palavras de inclusão/exclusão para as próximas sincronizações.
                </CardDescription>
              </div>
              <Button type="button" variant="outline" onClick={() => router.push("/")}>
                Voltar ao Dashboard
              </Button>
            </div>
          </CardHeader>
        </Card>

        <Card className="border border-border/60">
          <CardHeader>
            <CardTitle className="text-base">Manutenção do Banco</CardTitle>
            <CardDescription>
              Ações de limpeza aplicadas sobre as vagas já persistidas.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="rounded-md border border-amber-400/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-300">
              <strong>Limpeza de assertividade:</strong> remove permanentemente do banco todas as
              vagas <em>não analisadas</em> (pending, ready_for_ai, discarded) que não contenham ao
              menos 3 termos únicos das suas <code>include_keywords</code>. Vagas com status{" "}
              <em>analyzed</em> são preservadas. A operação roda em background e não pode ser
              desfeita.
            </div>
            <Button
              type="button"
              variant="destructive"
              onClick={() => void onCleanupAssertiveness()}
              disabled={cleaningUp}
            >
              {cleaningUp ? <Loader2 className="animate-spin" /> : null}
              Limpar vagas sem assertividade
            </Button>
          </CardContent>
        </Card>

        <Card className="border border-border/60">
          <CardHeader>
            <CardTitle className="text-base">Formulário de Configuração</CardTitle>
            <CardDescription>Use um termo por linha em cada campo.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            {loading ? (
              <p className="text-sm text-muted-foreground">Carregando configurações...</p>
            ) : null}

            {!loading && !hasLoadedConfig ? (
              <p className="text-sm text-destructive">Não foi possível carregar a configuração atual.</p>
            ) : null}

            {!loading && hasLoadedConfig ? (
              <>
                <div className="space-y-2">
                  <label className="text-sm font-medium" htmlFor="search-terms">
                    search_terms
                  </label>
                  <Textarea
                    id="search-terms"
                    value={searchTerms}
                    onChange={(event) => setSearchTerms(event.target.value)}
                    placeholder="python\nbackend\nfull stack"
                  />
                </div>

                <div className="space-y-2">
                  <label className="text-sm font-medium" htmlFor="include-keywords">
                    include_keywords
                  </label>
                  <Textarea
                    id="include-keywords"
                    value={includeKeywords}
                    onChange={(event) => setIncludeKeywords(event.target.value)}
                    placeholder="remoto\nclt\nsenior"
                  />
                </div>

                <div className="space-y-2">
                  <label className="text-sm font-medium" htmlFor="exclude-keywords">
                    exclude_keywords
                  </label>
                  <Textarea
                    id="exclude-keywords"
                    value={excludeKeywords}
                    onChange={(event) => setExcludeKeywords(event.target.value)}
                    placeholder="presencial\njunior"
                  />
                </div>

                <div className="flex flex-wrap gap-2">
                  <Button type="button" onClick={onSave} disabled={saving}>
                    {saving ? <Loader2 className="animate-spin" /> : null}
                    Salvar Configurações
                  </Button>
                  <Button type="button" variant="outline" onClick={onSyncIngest} disabled={ingesting}>
                    {ingesting ? <Loader2 className="animate-spin" /> : null}
                    Sincronizar Vagas
                  </Button>
                  <Button type="button" variant="secondary" onClick={onSyncAnalyze} disabled={analyzing}>
                    {analyzing ? <Loader2 className="animate-spin" /> : null}
                    Rodar Análise IA
                  </Button>
                </div>
              </>
            ) : null}
          </CardContent>
        </Card>
      </section>
    </main>
  );
}
