"use client";

import { useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  Check,
  Edit3,
  Eye,
  FilePlus2,
  FileText,
  FolderInput,
  Library,
  Loader2,
  RefreshCw,
  Search,
  Trash2,
  UploadCloud,
  X,
} from "lucide-react";
import type { DocumentResponse } from "@/lib/api";
import { formatBytes } from "@/lib/highlight";

export type StudioTab = "upload" | "write" | "browse";

export interface EditDraft {
  docId: number | null;
  title: string;
  externalId: string;
  content: string;
  metadataText: string;
}

interface DocumentStudioProps {
  activeTab: StudioTab;
  onTabChange: (tab: StudioTab) => void;
  documents: DocumentResponse[];
  loadingDocs: boolean;
  onRefreshDocs: () => void;
  onUploadFiles: (files: File[]) => Promise<void>;
  onImportDirectory: (dir: string) => Promise<void>;
  draft: EditDraft;
  onDraftChange: (draft: EditDraft) => void;
  onSaveDraft: () => Promise<void>;
  onCancelEdit: () => void;
  onStartEdit: (docId: number) => void;
  onDeleteDoc: (docId: number) => Promise<void>;
  onInspectDoc: (doc: DocumentResponse) => void;
}

const TABS: { id: StudioTab; label: string; icon: typeof UploadCloud }[] = [
  { id: "upload", label: "Upload Docs", icon: UploadCloud },
  { id: "write", label: "Add / Edit", icon: FilePlus2 },
  { id: "browse", label: "All Docs", icon: Library },
];

export function DocumentStudio({
  activeTab,
  onTabChange,
  documents,
  loadingDocs,
  onRefreshDocs,
  onUploadFiles,
  onImportDirectory,
  draft,
  onDraftChange,
  onSaveDraft,
  onCancelEdit,
  onStartEdit,
  onDeleteDoc,
  onInspectDoc,
}: DocumentStudioProps) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [queuedFiles, setQueuedFiles] = useState<File[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);

  const [dirPath, setDirPath] = useState("");
  const [importingDir, setImportingDir] = useState(false);

  const [savingDoc, setSavingDoc] = useState(false);
  const [docFilter, setDocFilter] = useState("");
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const metadataValid = useMemo(() => {
    try {
      const parsed = JSON.parse(draft.metadataText.trim() || "{}");
      return typeof parsed === "object" && parsed !== null && !Array.isArray(parsed);
    } catch {
      return false;
    }
  }, [draft.metadataText]);

  const filteredDocs = useMemo(() => {
    const q = docFilter.trim().toLowerCase();
    if (!q) return documents;
    return documents.filter(
      (d) =>
        d.title.toLowerCase().includes(q) ||
        (d.external_id || "").toLowerCase().includes(q) ||
        String(d.doc_id).includes(q)
    );
  }, [documents, docFilter]);

  const addFiles = (incomingList: FileList | null) => {
    const incoming = Array.from(incomingList || []);
    if (!incoming.length) return;
    setQueuedFiles((prev) => {
      const seen = new Set(prev.map((f) => `${f.name}:${f.size}`));
      const next = [...prev];
      for (const file of incoming) {
        if (!seen.has(`${file.name}:${file.size}`)) {
          seen.add(`${file.name}:${file.size}`);
          next.push(file);
        }
      }
      return next;
    });
  };

  const handleUploadSubmit = async () => {
    if (!queuedFiles.length) return;
    setUploading(true);
    try {
      await onUploadFiles(queuedFiles);
      setQueuedFiles([]);
    } finally {
      setUploading(false);
    }
  };

  const handleImportDir = async () => {
    const cleaned = dirPath.trim();
    if (!cleaned) return;
    setImportingDir(true);
    try {
      await onImportDirectory(cleaned);
    } finally {
      setImportingDir(false);
    }
  };

  const handleSaveForm = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!metadataValid) return;
    setSavingDoc(true);
    try {
      await onSaveDraft();
    } finally {
      setSavingDoc(false);
    }
  };

  const handleDelete = async (docId: number) => {
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

  return (
    <motion.section
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.32, delay: 0.06, ease: "easeOut" }}
      className="rounded-2xl border border-slate-800/90 bg-[#0b1120]/90 p-5 shadow-2xl shadow-black/30 backdrop-blur-xl sm:p-6"
    >
      {/* Segmented Sliding Tabs */}
      <div className="mb-5 grid grid-cols-3 gap-1.5 rounded-xl border border-slate-800 bg-[#060913] p-1">
        {TABS.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => onTabChange(tab.id)}
              className={`relative z-10 flex items-center justify-center gap-1.5 rounded-lg px-2.5 py-2 text-xs font-semibold transition-colors ${
                isActive ? "text-white" : "text-slate-400 hover:text-slate-200"
              }`}
            >
              {isActive && (
                <motion.span
                  layoutId="studioTabPill"
                  transition={{ type: "spring", stiffness: 440, damping: 32 }}
                  className="absolute inset-0 -z-10 rounded-lg bg-gradient-to-r from-blue-600 to-indigo-600 shadow-md shadow-blue-600/25"
                />
              )}
              <Icon className="h-3.5 w-3.5" />
              <span className="truncate">{tab.label}</span>
            </button>
          );
        })}
      </div>

      <AnimatePresence mode="wait">
        {activeTab === "upload" && (
          <motion.div
            key="upload-tab"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.18 }}
          >
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept=".pdf,.docx,.txt,.md,.csv,.json,.log,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain,text/markdown"
              className="hidden"
              onChange={(e) => {
                addFiles(e.target.files);
                e.target.value = "";
              }}
            />

            {/* Animated Dropzone */}
            <motion.div
              role="button"
              tabIndex={0}
              whileHover={{ scale: 1.005 }}
              whileTap={{ scale: 0.995 }}
              animate={{
                borderColor: dragOver
                  ? "rgba(59, 130, 246, 0.9)"
                  : "rgba(71, 85, 105, 0.7)",
                backgroundColor: dragOver
                  ? "rgba(59, 130, 246, 0.12)"
                  : "rgba(6, 9, 19, 0.65)",
              }}
              onClick={() => fileInputRef.current?.click()}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  fileInputRef.current?.click();
                }
              }}
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragOver(false);
                addFiles(e.dataTransfer.files);
              }}
              className="cursor-pointer rounded-2xl border-2 border-dashed px-5 py-7 text-center transition focus:outline-none focus:ring-4 focus:ring-blue-500/20"
            >
              <div className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-2xl border border-blue-500/25 bg-blue-500/12 text-blue-400">
                <UploadCloud className="h-5 w-5" />
              </div>
              <p className="font-display text-sm font-bold text-slate-100">
                Drop PDF, Word, Markdown, or text files
              </p>
              <p className="mt-1 text-xs text-slate-400">
                or click to browse ·{" "}
                <span className="font-mono text-[11px] text-slate-300">
                  .pdf .docx .txt .md .csv .json .log
                </span>
              </p>
            </motion.div>

            {/* Queued Files */}
            <AnimatePresence>
              {queuedFiles.length > 0 && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  exit={{ opacity: 0, height: 0 }}
                  className="mt-3 space-y-1.5 overflow-hidden"
                >
                  {queuedFiles.map((file, idx) => (
                    <motion.div
                      key={`${file.name}-${file.size}`}
                      layout
                      initial={{ opacity: 0, x: -10 }}
                      animate={{ opacity: 1, x: 0 }}
                      exit={{ opacity: 0, x: 10 }}
                      className="flex items-center justify-between gap-2 rounded-xl border border-slate-800 bg-[#060913] px-3 py-2 text-xs"
                    >
                      <div className="flex min-w-0 items-center gap-2">
                        <FileText className="h-3.5 w-3.5 shrink-0 text-blue-400" />
                        <span className="truncate font-medium text-slate-200">
                          {file.name}
                        </span>
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        <span className="font-mono text-[11px] text-slate-400">
                          {formatBytes(file.size)}
                        </span>
                        <button
                          type="button"
                          onClick={() =>
                            setQueuedFiles((prev) =>
                              prev.filter((_, i) => i !== idx)
                            )
                          }
                          className="rounded p-0.5 text-slate-400 transition hover:bg-slate-800 hover:text-rose-300"
                          aria-label={`Remove ${file.name}`}
                        >
                          <X className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </motion.div>
                  ))}
                </motion.div>
              )}
            </AnimatePresence>

            <div className="mt-3.5 flex gap-2">
              <motion.button
                type="button"
                whileTap={{ scale: 0.98 }}
                disabled={!queuedFiles.length || uploading}
                onClick={handleUploadSubmit}
                className="inline-flex flex-1 items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 px-4 py-2.5 text-xs font-semibold text-white shadow-lg shadow-blue-600/20 transition hover:from-blue-500 hover:to-indigo-500 disabled:cursor-not-allowed disabled:opacity-45"
              >
                {uploading ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    Uploading &amp; Indexing...
                  </>
                ) : (
                  <>
                    <UploadCloud className="h-3.5 w-3.5" />
                    Upload &amp; Index{" "}
                    {queuedFiles.length > 0 ? `(${queuedFiles.length})` : ""}
                  </>
                )}
              </motion.button>
              {queuedFiles.length > 0 && (
                <button
                  type="button"
                  onClick={() => setQueuedFiles([])}
                  className="rounded-xl border border-slate-700 bg-slate-800/70 px-3.5 py-2.5 text-xs font-semibold text-slate-300 transition hover:bg-slate-700"
                >
                  Clear
                </button>
              )}
            </div>

            <div className="my-5 h-px bg-slate-800/90" />

            {/* Folder Import */}
            <div>
              <label
                htmlFor="dirPathInput"
                className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-slate-300"
              >
                <FolderInput className="h-3.5 w-3.5 text-slate-400" />
                Import Local Server Folder
              </label>
              <div className="flex gap-2">
                <input
                  id="dirPathInput"
                  type="text"
                  value={dirPath}
                  onChange={(e) => setDirPath(e.target.value)}
                  placeholder="e.g. U:\documents"
                  className="flex-1 rounded-xl border border-slate-700/80 bg-[#060913] px-3 py-2 font-mono text-xs text-slate-100 placeholder:text-slate-500 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                />
                <button
                  type="button"
                  disabled={!dirPath.trim() || importingDir}
                  onClick={handleImportDir}
                  className="inline-flex items-center gap-1.5 rounded-xl border border-slate-700 bg-slate-800/80 px-3.5 py-2 text-xs font-semibold text-slate-200 transition hover:border-slate-600 hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-45"
                >
                  {importingDir ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <FolderInput className="h-3.5 w-3.5" />
                  )}
                  Import
                </button>
              </div>
            </div>
          </motion.div>
        )}

        {activeTab === "write" && (
          <motion.form
            key="write-tab"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.18 }}
            onSubmit={handleSaveForm}
            className="space-y-3"
          >
            <div>
              <label className="mb-1 block text-xs font-semibold text-slate-300">
                Title *
              </label>
              <input
                type="text"
                required
                value={draft.title}
                onChange={(e) =>
                  onDraftChange({ ...draft, title: e.target.value })
                }
                placeholder="Document title"
                className="w-full rounded-xl border border-slate-700/80 bg-[#060913] px-3 py-2 text-xs text-slate-100 placeholder:text-slate-500 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
              />
            </div>

            <div>
              <label className="mb-1 block text-xs font-semibold text-slate-300">
                External ID (optional upsert key)
              </label>
              <input
                type="text"
                disabled={draft.docId !== null}
                value={draft.externalId}
                onChange={(e) =>
                  onDraftChange({ ...draft, externalId: e.target.value })
                }
                placeholder="e.g. policy-2026-01"
                className="w-full rounded-xl border border-slate-700/80 bg-[#060913] px-3 py-2 font-mono text-xs text-slate-100 placeholder:text-slate-500 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 disabled:opacity-50"
              />
            </div>

            <div>
              <label className="mb-1 block text-xs font-semibold text-slate-300">
                Content *
              </label>
              <textarea
                required
                rows={6}
                value={draft.content}
                onChange={(e) =>
                  onDraftChange({ ...draft, content: e.target.value })
                }
                placeholder="Paste or type document text..."
                className="w-full rounded-xl border border-slate-700/80 bg-[#060913] px-3 py-2 text-xs leading-relaxed text-slate-100 placeholder:text-slate-500 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
              />
            </div>

            <div>
              <div className="mb-1 flex items-center justify-between">
                <label className="text-xs font-semibold text-slate-300">
                  Metadata JSON
                </label>
                <span
                  className={`font-mono text-[10px] ${
                    metadataValid ? "text-emerald-400" : "text-rose-400"
                  }`}
                >
                  {metadataValid ? "valid JSON" : "invalid JSON"}
                </span>
              </div>
              <input
                type="text"
                value={draft.metadataText}
                onChange={(e) =>
                  onDraftChange({ ...draft, metadataText: e.target.value })
                }
                placeholder='{"category": "engineering"}'
                className="w-full rounded-xl border border-slate-700/80 bg-[#060913] px-3 py-2 font-mono text-xs text-slate-100 placeholder:text-slate-500 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
              />
            </div>

            <div className="flex gap-2 pt-1">
              <button
                type="submit"
                disabled={savingDoc || !metadataValid}
                className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 px-4 py-2.5 text-xs font-semibold text-white shadow-lg shadow-blue-600/20 transition hover:from-blue-500 hover:to-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {savingDoc ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Check className="h-3.5 w-3.5" />
                )}
                {draft.docId !== null
                  ? `Update Doc #${draft.docId}`
                  : "Index Document"}
              </button>
              {draft.docId !== null && (
                <button
                  type="button"
                  onClick={onCancelEdit}
                  className="rounded-xl border border-slate-700 bg-slate-800/80 px-3.5 py-2.5 text-xs font-semibold text-slate-300 transition hover:bg-slate-700"
                >
                  Cancel
                </button>
              )}
            </div>
          </motion.form>
        )}

        {activeTab === "browse" && (
          <motion.div
            key="browse-tab"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.18 }}
          >
            <div className="mb-3 flex items-center gap-2">
              <div className="relative flex-1">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-500" />
                <input
                  type="text"
                  value={docFilter}
                  onChange={(e) => setDocFilter(e.target.value)}
                  placeholder="Filter indexed docs..."
                  className="w-full rounded-lg border border-slate-800 bg-[#060913] py-1.5 pl-8 pr-3 text-xs text-slate-200 placeholder:text-slate-500 focus:border-blue-500 focus:outline-none"
                />
              </div>
              <button
                type="button"
                onClick={onRefreshDocs}
                disabled={loadingDocs}
                className="inline-flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-800/80 px-2.5 py-1.5 text-xs font-medium text-slate-200 transition hover:bg-slate-700"
              >
                <RefreshCw
                  className={`h-3 w-3 ${loadingDocs ? "animate-spin" : ""}`}
                />
                Refresh
              </button>
            </div>

            {filteredDocs.length === 0 ? (
              <div className="rounded-xl border border-dashed border-slate-800 bg-[#060913]/50 py-10 text-center text-xs text-slate-400">
                {documents.length === 0
                  ? "No documents indexed in SQLite yet."
                  : "No documents match that filter."}
              </div>
            ) : (
              <div className="max-h-[440px] space-y-2 overflow-y-auto pr-1">
                {filteredDocs.map((doc) => {
                  const ext =
                    typeof doc.metadata?.extension === "string"
                      ? doc.metadata.extension
                      : null;
                  return (
                    <motion.div
                      key={doc.doc_id}
                      layout
                      className="flex items-center justify-between gap-2 rounded-xl border border-slate-800/90 bg-[#060913]/85 px-3 py-2.5 transition-colors hover:border-slate-700"
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5">
                          <span className="truncate text-xs font-semibold text-slate-100">
                            {doc.title}
                          </span>
                          {ext && (
                            <span className="rounded border border-slate-700/80 bg-slate-800/80 px-1.5 py-0.2 font-mono text-[10px] uppercase text-slate-300">
                              {ext.replace(".", "")}
                            </span>
                          )}
                        </div>
                        <div className="mt-0.5 truncate font-mono text-[11px] text-slate-400">
                          id={doc.doc_id} · {doc.doc_length} tokens
                          {doc.external_id ? ` · ${doc.external_id}` : ""}
                        </div>
                      </div>

                      <div className="flex shrink-0 items-center gap-1">
                        <button
                          type="button"
                          onClick={() => onInspectDoc(doc)}
                          className="rounded-lg border border-slate-700/80 bg-slate-800/70 p-1.5 text-slate-300 transition hover:border-blue-500/50 hover:text-blue-300"
                          title="Inspect Document"
                        >
                          <Eye className="h-3.5 w-3.5" />
                        </button>
                        <button
                          type="button"
                          onClick={() => onStartEdit(doc.doc_id)}
                          className="rounded-lg border border-slate-700/80 bg-slate-800/70 p-1.5 text-slate-300 transition hover:border-slate-600 hover:text-white"
                          title="Edit Document"
                        >
                          <Edit3 className="h-3.5 w-3.5" />
                        </button>
                        <button
                          type="button"
                          disabled={deletingId === doc.doc_id}
                          onMouseLeave={() => {
                            if (confirmDeleteId === doc.doc_id) {
                              setConfirmDeleteId(null);
                            }
                          }}
                          onClick={() => handleDelete(doc.doc_id)}
                          className={`rounded-lg border p-1.5 transition ${
                            confirmDeleteId === doc.doc_id
                              ? "border-rose-500 bg-rose-600 text-white"
                              : "border-rose-500/30 bg-rose-500/10 text-rose-300 hover:bg-rose-500/20"
                          }`}
                          title={
                            confirmDeleteId === doc.doc_id
                              ? "Click again to delete"
                              : "Delete Document"
                          }
                        >
                          {deletingId === doc.doc_id ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <Trash2 className="h-3.5 w-3.5" />
                          )}
                        </button>
                      </div>
                    </motion.div>
                  );
                })}
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </motion.section>
  );
}

