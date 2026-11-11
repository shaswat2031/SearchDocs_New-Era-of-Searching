"use client";

import { useCallback, useEffect, useState } from "react";
import { MotionConfig, motion } from "framer-motion";
import {
  BookOpen,
  ExternalLink,
  Loader2,
  RefreshCw,
  Terminal,
} from "lucide-react";
import {
  createDocument,
  deleteDocument,
  fetchStats,
  getApiBase,
  getDocument,
  importDirectory,
  listDocuments,
  rebuildIndex,
  searchDocuments,
  updateDocument,
  uploadFiles,
  type DocumentResponse,
  type SearchApiResponse,
  type SearchHitResponse,
  type StatsResponse,
} from "@/lib/api";
import { DocumentInspectorModal } from "./DocumentInspectorModal";
import {
  DocumentStudio,
  type EditDraft,
  type StudioTab,
} from "./DocumentStudio";
import { SearchConsole } from "./SearchConsole";
import { StatsStrip } from "./StatsStrip";
import { ToastStack, type ToastItem } from "./ToastStack";

const EMPTY_DRAFT: EditDraft = {
  docId: null,
  title: "",
  externalId: "",
  content: "",
  metadataText: "{}",
};

const INITIAL_STATS: StatsResponse = {
  total_documents: 0,
  vocabulary_size: 0,
  total_tokens: 0,
  avg_doc_length: 0,
  parallel_active: false,
  parallel_workers: 0,
};

export function SearchCoreApp() {
  const [stats, setStats] = useState<StatsResponse>(INITIAL_STATS);
  const [loadingStats, setLoadingStats] = useState(true);
  const [rebuilding, setRebuilding] = useState(false);

  const [query, setQuery] = useState("");
  const [operator, setOperator] = useState<"AND" | "OR">("AND");
  const [parallel, setParallel] = useState(false);
  const [limit, setLimit] = useState(10);
  const [offset, setOffset] = useState(0);
  const [searching, setSearching] = useState(false);
  const [searchResult, setSearchResult] = useState<SearchApiResponse | null>(
    null
  );

  const [activeTab, setActiveTab] = useState<StudioTab>("upload");
  const [documents, setDocuments] = useState<DocumentResponse[]>([]);
  const [loadingDocs, setLoadingDocs] = useState(false);
  const [draft, setDraft] = useState<EditDraft>(EMPTY_DRAFT);

  const [inspectedHit, setInspectedHit] = useState<SearchHitResponse | null>(
    null
  );
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const [docsUrl, setDocsUrl] = useState<string>("http://127.0.0.1:8000/docs");

  useEffect(() => {
    const base = getApiBase();
    setDocsUrl(base ? `${base}/docs` : "/docs");
  }, []);

  const pushToast = useCallback(
    (type: ToastItem["type"], message: string) => {
      const id = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
      setToasts((prev) => [...prev.slice(-3), { id, type, message }]);
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
      }, 4500);
    },
    []
  );

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const refreshStats = useCallback(async () => {
    try {
      setLoadingStats(true);
      const s = await fetchStats();
      setStats(s);
    } catch (err) {
      pushToast(
        "error",
        err instanceof Error ? err.message : "Failed to load stats."
      );
    } finally {
      setLoadingStats(false);
    }
  }, [pushToast]);

  const refreshDocuments = useCallback(async () => {
    try {
      setLoadingDocs(true);
      const list = await listDocuments(200, 0);
      setDocuments(list);
    } catch (err) {
      pushToast(
        "error",
        err instanceof Error ? err.message : "Failed to load documents."
      );
    } finally {
      setLoadingDocs(false);
    }
  }, [pushToast]);

  useEffect(() => {
    refreshStats();
    refreshDocuments();
  }, [refreshStats, refreshDocuments]);

  const runSearch = useCallback(
    async (nextOffset = 0, explicitQuery?: string) => {
      const targetQuery = (explicitQuery ?? query).trim();
      if (!targetQuery) {
        pushToast("error", "Enter a search query first.");
        return;
      }
      setSearching(true);
      setOffset(nextOffset);
      try {
        const res = await searchDocuments({
          q: targetQuery,
          limit,
          offset: nextOffset,
          operator,
          include_content: true,
          parallel,
        });
        setSearchResult(res);
        await refreshStats();
      } catch (err) {
        pushToast(
          "error",
          err instanceof Error ? err.message : "Search failed."
        );
      } finally {
        setSearching(false);
      }
    },
    [query, limit, operator, parallel, pushToast, refreshStats]
  );

  const handleUploadFiles = async (files: File[]) => {
    try {
      const created = await uploadFiles(files);
      pushToast(
        "success",
        `Uploaded and indexed ${created.length} document${created.length === 1 ? "" : "s"}.`
      );
      await Promise.all([refreshStats(), refreshDocuments()]);
      if (query.trim()) {
        await runSearch(0);
      }
    } catch (err) {
      pushToast(
        "error",
        err instanceof Error ? err.message : "File upload failed."
      );
    }
  };

  const handleImportDirectory = async (directory: string) => {
    try {
      const res = await importDirectory(directory);
      pushToast(
        "success",
        `Imported ${res.imported_count} document(s) from folder.`
      );
      await Promise.all([refreshStats(), refreshDocuments()]);
      if (query.trim()) {
        await runSearch(0);
      }
    } catch (err) {
      pushToast(
        "error",
        err instanceof Error ? err.message : "Directory import failed."
      );
    }
  };

  const handleStartEdit = async (docId: number) => {
    try {
      const doc = await getDocument(docId);
      setDraft({
        docId: doc.doc_id,
        title: doc.title,
        externalId: doc.external_id || "",
        content: doc.content,
        metadataText: JSON.stringify(doc.metadata || {}, null, 2),
      });
      setActiveTab("write");
      pushToast("info", `Editing document #${doc.doc_id}`);
    } catch (err) {
      pushToast(
        "error",
        err instanceof Error ? err.message : "Could not load document."
      );
    }
  };

  const handleSaveDraft = async () => {
    let parsedMeta: Record<string, unknown> = {};
    try {
      parsedMeta = JSON.parse(draft.metadataText.trim() || "{}");
    } catch {
      pushToast("error", "Metadata must be valid JSON.");
      return;
    }

    try {
      if (draft.docId !== null) {
        const updated = await updateDocument(draft.docId, {
          title: draft.title.trim(),
          content: draft.content,
          metadata: parsedMeta,
        });
        pushToast("success", `Updated document #${updated.doc_id}.`);
      } else {
        const created = await createDocument({
          title: draft.title.trim(),
          content: draft.content,
          external_id: draft.externalId.trim() || null,
          metadata: parsedMeta,
        });
        pushToast("success", `Indexed document #${created.doc_id}.`);
      }
      setDraft(EMPTY_DRAFT);
      await Promise.all([refreshStats(), refreshDocuments()]);
      if (query.trim()) {
        await runSearch(offset);
      }
    } catch (err) {
      pushToast(
        "error",
        err instanceof Error ? err.message : "Could not save document."
      );
    }
  };

  const handleDeleteDoc = async (docId: number) => {
    try {
      await deleteDocument(docId);
      pushToast("success", `Deleted document #${docId}.`);
      if (inspectedHit?.doc_id === docId) {
        setInspectedHit(null);
      }
      await Promise.all([refreshStats(), refreshDocuments()]);
      if (query.trim()) {
        await runSearch(0);
      }
    } catch (err) {
      pushToast(
        "error",
        err instanceof Error ? err.message : "Delete failed."
      );
    }
  };

  const handleRebuildIndex = async () => {
    setRebuilding(true);
    try {
      const res = await rebuildIndex();
      pushToast(
        "success",
        `Rebuilt index: ${res.documents_reindexed} docs, ${res.vocabulary_size} terms.`
      );
      await refreshStats();
    } catch (err) {
      pushToast(
        "error",
        err instanceof Error ? err.message : "Index rebuild failed."
      );
    } finally {
      setRebuilding(false);
    }
  };

  const handleInspectDocumentRecord = (doc: DocumentResponse) => {
    setInspectedHit({
      doc_id: doc.doc_id,
      external_id: doc.external_id,
      title: doc.title,
      score: 0,
      snippet: "",
      match_count: 0,
      snippets: [],
      content: doc.content,
      metadata: doc.metadata,
    });
  };

  return (
    <MotionConfig reducedMotion="user">
      <div className="relative min-h-screen overflow-x-hidden bg-[#060913] text-slate-100">
        {/* Atmospheric Radial Glows */}
        <div className="pointer-events-none fixed inset-0 overflow-hidden">
          <div className="absolute -top-40 left-[8%] h-[420px] w-[620px] rounded-full bg-blue-600/14 blur-[120px]" />
          <div className="absolute -top-32 right-[6%] h-[360px] w-[520px] rounded-full bg-emerald-500/10 blur-[120px]" />
          <div className="absolute bottom-0 left-1/2 h-[300px] w-[680px] -translate-x-1/2 rounded-full bg-indigo-600/10 blur-[140px]" />
        </div>

        {/* Sticky Glass Topbar */}
        <header className="sticky top-0 z-30 border-b border-slate-800/80 bg-[#060913]/80 backdrop-blur-xl">
          <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-4 py-3.5 sm:px-6">
            <div className="flex items-center gap-3">
              <motion.div
                whileHover={{ rotate: 4, scale: 1.04 }}
                transition={{ type: "spring", stiffness: 400, damping: 20 }}
                className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 via-indigo-500 to-emerald-400 font-display text-sm font-extrabold tracking-tight text-white shadow-lg shadow-blue-500/25"
              >
                SC
              </motion.div>
              <div>
                <div className="flex items-center gap-2">
                  <h1 className="font-display text-lg font-bold tracking-tight text-white">
                    SearchCore
                  </h1>
                  <span className="hidden rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 font-mono text-[10px] font-semibold text-emerald-300 sm:inline-flex">
                    BM25 + SQLite WAL
                  </span>
                </div>
                <p className="text-xs text-slate-400">
                  Positional Inverted Index · Boolean &amp; Phrase Engine ·
                  Multi-Process Sharding
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2.5">
              <motion.button
                type="button"
                whileTap={{ scale: 0.97 }}
                disabled={rebuilding}
                onClick={handleRebuildIndex}
                className="inline-flex items-center gap-1.5 rounded-xl border border-slate-700/80 bg-slate-900/90 px-3.5 py-2 text-xs font-semibold text-slate-200 transition hover:border-slate-600 hover:bg-slate-800 disabled:opacity-55"
              >
                {rebuilding ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-400" />
                ) : (
                  <RefreshCw className="h-3.5 w-3.5 text-blue-400" />
                )}
                Rebuild Index
              </motion.button>

              <a
                href={docsUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 rounded-xl border border-slate-700/80 bg-slate-900/90 px-3.5 py-2 text-xs font-semibold text-slate-200 transition hover:border-blue-500/40 hover:bg-slate-800 hover:text-white"
              >
                <Terminal className="h-3.5 w-3.5 text-emerald-400" />
                Swagger API
                <ExternalLink className="h-3 w-3 text-slate-400" />
              </a>
            </div>
          </div>
        </header>

        {/* Main Workspace */}
        <main className="relative z-10 mx-auto max-w-7xl space-y-6 px-4 py-6 pb-16 sm:px-6">
          <StatsStrip stats={stats} loading={loadingStats} />

          <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-12">
            <div className="lg:col-span-7">
              <SearchConsole
                query={query}
                onQueryChange={setQuery}
                operator={operator}
                onOperatorChange={setOperator}
                parallel={parallel}
                onParallelChange={setParallel}
                limit={limit}
                onLimitChange={setLimit}
                offset={offset}
                searching={searching}
                searchResult={searchResult}
                onSearch={(nextOffset = 0) => runSearch(nextOffset)}
                onInspectHit={(hit) => setInspectedHit(hit)}
                onEditDoc={handleStartEdit}
                onDeleteDoc={handleDeleteDoc}
              />
            </div>

            <div className="lg:col-span-5">
              <DocumentStudio
                activeTab={activeTab}
                onTabChange={(tab) => {
                  setActiveTab(tab);
                  if (tab === "browse") {
                    refreshDocuments();
                  }
                }}
                documents={documents}
                loadingDocs={loadingDocs}
                onRefreshDocs={refreshDocuments}
                onUploadFiles={handleUploadFiles}
                onImportDirectory={handleImportDirectory}
                draft={draft}
                onDraftChange={setDraft}
                onSaveDraft={handleSaveDraft}
                onCancelEdit={() => setDraft(EMPTY_DRAFT)}
                onStartEdit={handleStartEdit}
                onDeleteDoc={handleDeleteDoc}
                onInspectDoc={handleInspectDocumentRecord}
              />
            </div>
          </div>

          <footer className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-800/70 pt-4 text-[11px] text-slate-500">
            <span className="inline-flex items-center gap-1.5">
              <BookOpen className="h-3.5 w-3.5" />
              SearchCore Studio · Next.js + Tailwind CSS + Framer Motion
            </span>
            <span className="font-mono">
              Tip: Press <kbd className="text-slate-300">Ctrl+K</kbd> or{" "}
              <kbd className="text-slate-300">/</kbd> to focus search
            </span>
          </footer>
        </main>

        <DocumentInspectorModal
          hit={inspectedHit}
          query={searchResult?.query ?? query}
          onClose={() => setInspectedHit(null)}
          onEdit={handleStartEdit}
        />

        <ToastStack toasts={toasts} onDismiss={dismissToast} />
      </div>
    </MotionConfig>
  );
}
