"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  ChevronDown,
  ChevronUp,
  Edit3,
  FileText,
  Sparkles,
  X,
} from "lucide-react";
import type { SearchHitResponse } from "@/lib/api";
import { splitHighlightSegments } from "@/lib/highlight";
import { HighlightedText } from "./HighlightedText";

interface DocumentInspectorModalProps {
  hit: SearchHitResponse | null;
  query: string;
  onClose: () => void;
  onEdit: (docId: number) => void;
}

export function DocumentInspectorModal({
  hit,
  query,
  onClose,
  onEdit,
}: DocumentInspectorModalProps) {
  const [activeMatch, setActiveMatch] = useState(0);
  const markRefs = useRef<(HTMLElement | null)[]>([]);

  const totalInlineMatches = useMemo(() => {
    if (!hit?.content || !query) return 0;
    return splitHighlightSegments(hit.content, query).filter((s) => s.isMatch)
      .length;
  }, [hit?.content, query]);

  useEffect(() => {
    markRefs.current = [];
    setActiveMatch(0);
  }, [hit?.doc_id, query]);

  useEffect(() => {
    if (!hit) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [hit, onClose]);

  useEffect(() => {
    if (!hit || totalInlineMatches === 0) return;
    const el = markRefs.current[activeMatch];
    if (el) {
      el.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }, [activeMatch, hit, totalInlineMatches]);

  const jump = (delta: number) => {
    if (totalInlineMatches <= 0) return;
    setActiveMatch(
      (prev) => (prev + delta + totalInlineMatches) % totalInlineMatches
    );
  };

  const ext =
    typeof hit?.metadata?.extension === "string"
      ? hit.metadata.extension
      : null;

  return (
    <AnimatePresence>
      {hit && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18 }}
          onClick={onClose}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-md"
        >
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 14, scale: 0.97 }}
            transition={{ type: "spring", stiffness: 360, damping: 28 }}
            onClick={(e) => e.stopPropagation()}
            className="flex max-h-[88vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl border border-slate-700/80 bg-[#0b1120] shadow-2xl shadow-black/70"
          >
            {/* Header */}
            <div className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-800 bg-[#0f172a]/90 px-6 py-4">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-blue-500/15 text-blue-400">
                    <FileText className="h-4 w-4" />
                  </span>
                  <h3 className="font-display truncate text-lg font-bold text-slate-100">
                    {hit.title}
                  </h3>
                  {ext && (
                    <span className="rounded-md border border-slate-700 bg-slate-800/80 px-2 py-0.5 font-mono text-[11px] uppercase text-slate-300">
                      {ext.replace(".", "")}
                    </span>
                  )}
                </div>
                <div className="mt-1.5 flex flex-wrap items-center gap-3 font-mono text-xs text-slate-400">
                  <span>doc_id={hit.doc_id}</span>
                  {hit.external_id && <span>ext={hit.external_id}</span>}
                  <span className="inline-flex items-center gap-1 text-emerald-400">
                    <Sparkles className="h-3 w-3" />
                    BM25 {hit.score.toFixed(4)}
                  </span>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => {
                    const id = hit.doc_id;
                    onClose();
                    onEdit(id);
                  }}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800/80 px-3 py-1.5 text-xs font-semibold text-slate-200 transition hover:border-slate-600 hover:bg-slate-700"
                >
                  <Edit3 className="h-3.5 w-3.5" />
                  Edit Doc
                </button>
                <button
                  type="button"
                  onClick={onClose}
                  className="rounded-lg border border-slate-700/80 bg-slate-800/60 p-1.5 text-slate-400 transition hover:bg-slate-700 hover:text-white"
                  aria-label="Close document inspector"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>

            {/* Match Navigation Bar */}
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800/80 bg-[#080d1a] px-6 py-2.5 text-xs">
              <span className="font-mono text-slate-300">
                {totalInlineMatches > 0
                  ? `Match ${activeMatch + 1} of ${totalInlineMatches} highlighted in document`
                  : `${hit.match_count} match(es) indexed (check title or phrases)`}
              </span>
              {totalInlineMatches > 0 && (
                <div className="flex items-center gap-1.5">
                  <button
                    type="button"
                    onClick={() => jump(-1)}
                    className="inline-flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-800/80 px-2.5 py-1 font-medium text-slate-200 transition hover:border-blue-500/50 hover:bg-slate-700"
                  >
                    <ChevronUp className="h-3.5 w-3.5" />
                    Prev
                  </button>
                  <button
                    type="button"
                    onClick={() => jump(1)}
                    className="inline-flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-800/80 px-2.5 py-1 font-medium text-slate-200 transition hover:border-blue-500/50 hover:bg-slate-700"
                  >
                    <ChevronDown className="h-3.5 w-3.5" />
                    Next
                  </button>
                </div>
              )}
            </div>

            {/* Document Body */}
            <div className="flex-1 overflow-y-auto p-6">
              <pre className="whitespace-pre-wrap break-words font-sans text-sm leading-relaxed text-slate-200">
                <HighlightedText
                  text={hit.content || "(No document text content)"}
                  query={query}
                  activeMatchIndex={activeMatch}
                  markRefs={markRefs}
                />
              </pre>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

