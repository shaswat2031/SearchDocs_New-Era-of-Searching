"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowLeft,
  ArrowRight,
  ChevronDown,
  ChevronUp,
  Cpu,
  Edit3,
  Eye,
  FileText,
  Layers,
  Loader2,
  Search,
  Sparkles,
  Trash2,
  X,
  Zap,
} from "lucide-react";
import type { SearchApiResponse, SearchHitResponse } from "@/lib/api";
import { HighlightedText } from "./HighlightedText";

interface SearchConsoleProps {
  query: string;
  onQueryChange: (q: string) => void;
  operator: "AND" | "OR";
  onOperatorChange: (op: "AND" | "OR") => void;
  parallel: boolean;
  onParallelChange: (parallel: boolean) => void;
  limit: number;
  onLimitChange: (limit: number) => void;
  offset: number;
  searching: boolean;
  searchResult: SearchApiResponse | null;
  onSearch: (nextOffset?: number) => void;
  onInspectHit: (hit: SearchHitResponse) => void;
  onEditDoc: (docId: number) => void;
  onDeleteDoc: (docId: number) => Promise<void>;
}

const SYNTAX_TOKENS = [
  { label: '"exact phrase"', insert: '""' },
  { label: "AND", insert: " AND " },
  { label: "OR", insert: " OR " },
  { label: "AND NOT", insert: " AND NOT " },
  { label: "( )", insert: "()" },
];

export function SearchConsole({
  query,
  onQueryChange,
  operator,
  onOperatorChange,
  parallel,
  onParallelChange,
  limit,
  onLimitChange,
  offset,
  searching,
  searchResult,
  onSearch,
  onInspectHit,
  onEditDoc,
  onDeleteDoc,
}: SearchConsoleProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [expandedSnippets, setExpandedSnippets] = useState<
    Record<number, boolean>
  >({});
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        inputRef.current?.focus();
      } else if (
        e.key === "/" &&
        document.activeElement?.tagName !== "INPUT" &&
        document.activeElement?.tagName !== "TEXTAREA"
      ) {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const insertToken = (snippet: string) => {
    const input = inputRef.current;
    if (!input) {
      onQueryChange(`${query}${snippet}`);
      return;
    }
    const start = input.selectionStart ?? query.length;
    const end = input.selectionEnd ?? query.length;
    const next = query.slice(0, start) + snippet + query.slice(end);
    onQueryChange(next);
    requestAnimationFrame(() => {
      input.focus();
      const cursor =
        snippet === '""' || snippet === "()"
          ? start + 1
          : start + snippet.length;
      input.setSelectionRange(cursor, cursor);
    });
  };

  const handleConfirmDelete = async (docId: number) => {
    if (confirmDeleteId !== docId) {
      setConfirmDeleteId(docId);
      return;
    }
    setDeletingId(docId);
    try {
      await onDeleteDoc(docId);
    } finally {
      setDeletingId(null);
      setConfirmDeleteId(null);
    }
  };

  const totalHits = searchResult?.total_hits ?? 0;
  const hasPrev = offset > 0;
  const hasNext = offset + limit < totalHits;

  return (
    <motion.section
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.32, ease: "easeOut" }}
      className="rounded-2xl border border-slate-800/90 bg-[#0b1120]/90 p-5 shadow-2xl shadow-black/30 backdrop-blur-xl sm:p-6"
    >
      {/* Header */}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <span className="flex h-8 w-8 items-center justify-center rounded-xl border border-blue-500/30 bg-blue-500/15 text-blue-400">
            <Search className="h-4 w-4" />
          </span>
          <div>
            <h2 className="font-display text-base font-bold tracking-tight text-slate-100">
              Search Console
            </h2>
            <p className="text-xs text-slate-400">
              Positional phrase matching · Okapi BM25 ranking
            </p>
          </div>
        </div>

        <span
          className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 font-mono text-[11px] font-semibold uppercase tracking-wider ${
            (searchResult?.mode ?? (parallel ? "parallel" : "serial")) ===
            "parallel"
              ? "border-emerald-500/35 bg-emerald-500/15 text-emerald-300"
              : "border-blue-500/35 bg-blue-500/15 text-blue-300"
          }`}
        >
          <span
            className={`h-1.5 w-1.5 rounded-full ${
              (searchResult?.mode ?? (parallel ? "parallel" : "serial")) ===
              "parallel"
                ? "bg-emerald-400"
                : "bg-blue-400"
            }`}
          />
          {searchResult?.mode ?? (parallel ? "parallel" : "serial")}
        </span>
      </div>

      {/* Search Bar */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onSearch(0);
        }}
        className="group relative flex flex-col gap-2.5 sm:flex-row"
      >
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400 transition-colors group-focus-within:text-blue-400" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => onQueryChange(e.target.value)}
            placeholder='Search terms, "exact phrase", AND / OR / NOT, ( )...'
            autoComplete="off"
            className="w-full rounded-xl border border-slate-700/80 bg-[#060913] py-3 pl-10 pr-24 text-sm text-slate-100 placeholder:text-slate-500 shadow-inner transition focus:border-blue-500 focus:outline-none focus:ring-4 focus:ring-blue-500/15"
          />
          <div className="absolute right-2.5 top-1/2 flex -translate-y-1/2 items-center gap-1.5">
            {query && (
              <button
                type="button"
                onClick={() => {
                  onQueryChange("");
                  inputRef.current?.focus();
                }}
                className="rounded-md p-1 text-slate-400 transition hover:bg-slate-800 hover:text-slate-200"
                aria-label="Clear query"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
            <kbd className="hidden rounded-md border border-slate-700/80 bg-slate-900 px-1.5 py-0.5 font-mono text-[10px] text-slate-400 sm:inline-block">
              Ctrl K
            </kbd>
          </div>
        </div>

        <motion.button
          type="submit"
          disabled={searching}
          whileTap={{ scale: 0.97 }}
          className="inline-flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 px-5 py-3 text-sm font-semibold text-white shadow-lg shadow-blue-600/25 transition hover:from-blue-500 hover:to-indigo-500 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {searching ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Searching
            </>
          ) : (
            <>
              <Zap className="h-4 w-4" />
              Search
            </>
          )}
        </motion.button>
      </form>

      {/* Controls Bar */}
      <div className="mt-3.5 flex flex-wrap items-center justify-between gap-3 border-t border-slate-800/80 pt-3.5 text-xs">
        <div className="flex flex-wrap items-center gap-3">
          {/* Operator Segmented Pill */}
          <div className="flex items-center gap-2">
            <span className="font-medium text-slate-400">Default Op</span>
            <div className="relative flex rounded-lg border border-slate-800 bg-[#060913] p-0.5">
              {(["AND", "OR"] as const).map((op) => (
                <button
                  key={op}
                  type="button"
                  onClick={() => onOperatorChange(op)}
                  className={`relative z-10 rounded-md px-2.5 py-1 font-mono text-[11px] font-semibold transition-colors ${
                    operator === op
                      ? "text-white"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  {operator === op && (
                    <motion.span
                      layoutId="operatorPill"
                      transition={{
                        type: "spring",
                        stiffness: 450,
                        damping: 32,
                      }}
                      className="absolute inset-0 -z-10 rounded-md bg-blue-600 shadow-sm shadow-blue-600/40"
                    />
                  )}
                  {op}
                </button>
              ))}
            </div>
          </div>

          {/* Execution Mode Segmented Pill */}
          <div className="flex items-center gap-2">
            <span className="font-medium text-slate-400">Engine</span>
            <div className="relative flex rounded-lg border border-slate-800 bg-[#060913] p-0.5">
              {[
                { key: false, label: "Serial", icon: Layers },
                { key: true, label: "Parallel", icon: Cpu },
              ].map((item) => {
                const Icon = item.icon;
                const active = parallel === item.key;
                return (
                  <button
                    key={item.label}
                    type="button"
                    onClick={() => onParallelChange(item.key)}
                    className={`relative z-10 inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-[11px] font-semibold transition-colors ${
                      active
                        ? "text-white"
                        : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    {active && (
                      <motion.span
                        layoutId="enginePill"
                        transition={{
                          type: "spring",
                          stiffness: 450,
                          damping: 32,
                        }}
                        className={`absolute inset-0 -z-10 rounded-md shadow-sm ${
                          item.key
                            ? "bg-emerald-600 shadow-emerald-600/35"
                            : "bg-slate-700 shadow-black/30"
                        }`}
                      />
                    )}
                    <Icon className="h-3 w-3" />
                    {item.label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Limit Selector */}
          <label className="flex items-center gap-2 text-slate-400">
            <span className="font-medium">Limit</span>
            <select
              value={limit}
              onChange={(e) => onLimitChange(Number(e.target.value))}
              className="rounded-lg border border-slate-800 bg-[#060913] px-2.5 py-1 font-mono text-xs text-slate-200 focus:border-blue-500 focus:outline-none"
            >
              <option value={10}>10</option>
              <option value={25}>25</option>
              <option value={50}>50</option>
            </select>
          </label>
        </div>

        {/* Syntax Helper Chips */}
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[11px] text-slate-500">Insert:</span>
          {SYNTAX_TOKENS.map((chip) => (
            <button
              key={chip.label}
              type="button"
              onClick={() => insertToken(chip.insert)}
              className="rounded-md border border-slate-800 bg-[#060913] px-2 py-0.5 font-mono text-[11px] text-slate-300 transition hover:border-blue-500/50 hover:bg-blue-500/10 hover:text-blue-200"
            >
              {chip.label}
            </button>
          ))}
        </div>
      </div>

      {/* Results Header */}
      <div className="mt-5 mb-3 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-400">
        {searchResult ? (
          <>
            <span>
              <strong className="font-semibold text-slate-100">
                {searchResult.total_hits}
              </strong>{" "}
              matching document{searchResult.total_hits === 1 ? "" : "s"} for{" "}
              <code className="rounded bg-slate-800/90 px-1.5 py-0.5 font-mono text-[11px] text-blue-300">
                {searchResult.query}
              </code>
            </span>
            <span className="font-mono text-[11px] text-slate-400">
              {searchResult.took_ms.toFixed(2)} ms · {searchResult.mode}
            </span>
          </>
        ) : (
          <span>Ready to query indexed documents.</span>
        )}
      </div>

      {/* Search Results Body */}
      <div className="space-y-3">
        {searching && !searchResult ? (
          <div className="space-y-3">
            {[0, 1, 2].map((skeleton) => (
              <div
                key={skeleton}
                className="h-32 animate-pulse rounded-xl border border-slate-800 bg-[#060913]/80"
              />
            ))}
          </div>
        ) : !searchResult ? (
          <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-slate-800 bg-[#060913]/50 px-6 py-12 text-center">
            <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-2xl border border-blue-500/20 bg-blue-500/10 text-blue-400">
              <Sparkles className="h-5 w-5" />
            </div>
            <p className="font-display text-sm font-semibold text-slate-200">
              Search across PDFs, Word docs, Markdown, and text
            </p>
            <p className="mt-1 max-w-md text-xs leading-relaxed text-slate-400">
              Upload files or add a document in the right panel, then run
              keyword, quoted phrase, or boolean queries here.
            </p>
          </div>
        ) : searchResult.hits.length === 0 ? (
          <motion.div
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            className="rounded-xl border border-dashed border-slate-800 bg-[#060913]/60 px-6 py-10 text-center text-sm text-slate-400"
          >
            No documents matched{" "}
            <code className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-xs text-slate-200">
              {searchResult.query}
            </code>
            . Try switching default operator to <strong>OR</strong>.
          </motion.div>
        ) : (
          <AnimatePresence mode="popLayout">
            {searchResult.hits.map((hit, idx) => {
              const fragments =
                hit.snippets && hit.snippets.length > 0
                  ? hit.snippets
                  : hit.snippet
                    ? [hit.snippet]
                    : [];
              const isExpanded = Boolean(expandedSnippets[hit.doc_id]);
              const visibleFragments = isExpanded
                ? fragments
                : fragments.slice(0, 3);
              const extraCount = Math.max(0, fragments.length - 3);
              const ext =
                typeof hit.metadata?.extension === "string"
                  ? hit.metadata.extension
                  : null;
              const matchCount = hit.match_count || 0;

              return (
                <motion.article
                  key={`${hit.doc_id}-${searchResult.query}`}
                  layout
                  initial={{ opacity: 0, y: 14 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  transition={{
                    duration: 0.24,
                    delay: Math.min(idx * 0.04, 0.28),
                  }}
                  className="group rounded-xl border border-slate-800/90 bg-[#060913]/85 p-4 transition-colors hover:border-slate-700"
                >
                  {/* Hit Header */}
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <FileText className="h-4 w-4 shrink-0 text-blue-400" />
                        <h3 className="font-display truncate text-[15px] font-bold text-slate-100">
                          {hit.title}
                        </h3>
                        {ext && (
                          <span className="rounded border border-slate-700/80 bg-slate-800/80 px-1.5 py-0.5 font-mono text-[10px] uppercase text-slate-300">
                            {ext.replace(".", "")}
                          </span>
                        )}
                      </div>
                      <div className="mt-1 flex flex-wrap items-center gap-2 font-mono text-[11px] text-slate-400">
                        <span>doc_id={hit.doc_id}</span>
                        {hit.external_id && (
                          <>
                            <span className="text-slate-600">·</span>
                            <span className="truncate max-w-xs">
                              {hit.external_id}
                            </span>
                          </>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      <span className="rounded-full border border-blue-500/30 bg-blue-500/12 px-2.5 py-0.5 font-mono text-[11px] font-semibold text-blue-300">
                        {matchCount === 1
                          ? "1 match"
                          : `${matchCount} matches`}
                      </span>
                      <span className="rounded-full border border-emerald-500/35 bg-emerald-500/12 px-2.5 py-0.5 font-mono text-[11px] font-semibold text-emerald-300">
                        BM25 {hit.score.toFixed(4)}
                      </span>
                    </div>
                  </div>

                  {/* Multi-occurrence Snippets */}
                  {visibleFragments.length > 0 && (
                    <div className="mt-3 space-y-1.5">
                      <AnimatePresence initial={false}>
                        {visibleFragments.map((frag, fragIdx) => (
                          <motion.div
                            key={`${hit.doc_id}-frag-${fragIdx}`}
                            initial={{ opacity: 0, height: 0 }}
                            animate={{ opacity: 1, height: "auto" }}
                            exit={{ opacity: 0, height: 0 }}
                            transition={{ duration: 0.18 }}
                            className="rounded-r-lg border-l-2 border-blue-500/80 bg-[#0d1527] px-3 py-2 text-[13px] leading-relaxed text-slate-300"
                          >
                            <HighlightedText
                              text={frag}
                              query={searchResult.query}
                            />
                          </motion.div>
                        ))}
                      </AnimatePresence>
                    </div>
                  )}

                  {/* Actions */}
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    {extraCount > 0 && (
                      <button
                        type="button"
                        onClick={() =>
                          setExpandedSnippets((prev) => ({
                            ...prev,
                            [hit.doc_id]: !prev[hit.doc_id],
                          }))
                        }
                        className="inline-flex items-center gap-1 rounded-lg border border-slate-700/80 bg-slate-800/70 px-2.5 py-1 text-xs font-medium text-slate-200 transition hover:border-slate-600 hover:bg-slate-700"
                      >
                        {isExpanded ? (
                          <>
                            <ChevronUp className="h-3.5 w-3.5" />
                            Show fewer excerpts
                          </>
                        ) : (
                          <>
                            <ChevronDown className="h-3.5 w-3.5" />
                            Show {extraCount} more excerpt
                            {extraCount === 1 ? "" : "s"}
                          </>
                        )}
                      </button>
                    )}

                    <button
                      type="button"
                      onClick={() => onInspectHit(hit)}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-blue-500/30 bg-blue-500/12 px-2.5 py-1 text-xs font-semibold text-blue-300 transition hover:border-blue-400/50 hover:bg-blue-500/20"
                    >
                      <Eye className="h-3.5 w-3.5" />
                      Inspect Full Doc &amp; Matches
                    </button>

                    <button
                      type="button"
                      onClick={() => onEditDoc(hit.doc_id)}
                      className="inline-flex items-center gap-1 rounded-lg border border-slate-700/80 bg-slate-800/70 px-2.5 py-1 text-xs font-medium text-slate-300 transition hover:border-slate-600 hover:bg-slate-700 hover:text-white"
                    >
                      <Edit3 className="h-3.5 w-3.5" />
                      Edit
                    </button>

                    <button
                      type="button"
                      disabled={deletingId === hit.doc_id}
                      onMouseLeave={() => {
                        if (confirmDeleteId === hit.doc_id) {
                          setConfirmDeleteId(null);
                        }
                      }}
                      onClick={() => handleConfirmDelete(hit.doc_id)}
                      className={`inline-flex items-center gap-1 rounded-lg border px-2.5 py-1 text-xs font-medium transition ${
                        confirmDeleteId === hit.doc_id
                          ? "border-rose-500 bg-rose-600 text-white"
                          : "border-rose-500/30 bg-rose-500/10 text-rose-300 hover:bg-rose-500/20"
                      }`}
                    >
                      {deletingId === hit.doc_id ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Trash2 className="h-3.5 w-3.5" />
                      )}
                      {confirmDeleteId === hit.doc_id
                        ? "Confirm Delete"
                        : "Delete"}
                    </button>
                  </div>
                </motion.article>
              );
            })}
          </AnimatePresence>
        )}
      </div>

      {/* Pagination */}
      {searchResult && (hasPrev || hasNext) && (
        <div className="mt-4 flex items-center justify-between border-t border-slate-800/80 pt-3 text-xs text-slate-400">
          <span className="font-mono">
            Showing {offset + 1}–{Math.min(offset + limit, totalHits)} of{" "}
            {totalHits}
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={!hasPrev || searching}
              onClick={() => onSearch(Math.max(0, offset - limit))}
              className="inline-flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-800/80 px-3 py-1.5 font-medium text-slate-200 transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              Prev
            </button>
            <button
              type="button"
              disabled={!hasNext || searching}
              onClick={() => onSearch(offset + limit)}
              className="inline-flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-800/80 px-3 py-1.5 font-medium text-slate-200 transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Next
              <ArrowRight className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      )}
    </motion.section>
  );
}

