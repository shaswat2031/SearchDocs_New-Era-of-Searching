"use client";

import { useEffect } from "react";
import Link from "next/link";
import { ArrowLeft, ExternalLink, Terminal } from "lucide-react";

const FASTAPI_DOCS_URL =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "")
    ? `${process.env.NEXT_PUBLIC_API_BASE.replace(/\/$/, "")}/docs`
    : "http://127.0.0.1:8000/docs";

export default function DocsRedirectPage() {
  useEffect(() => {
    window.location.replace(FASTAPI_DOCS_URL);
  }, []);

  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-[#060913] px-4 text-slate-100">
      <div className="w-full max-w-md rounded-2xl border border-slate-800 bg-[#0b1120] p-6 text-center shadow-2xl">
        <div className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-xl border border-emerald-500/30 bg-emerald-500/15 text-emerald-400">
          <Terminal className="h-5 w-5" />
        </div>
        <h1 className="font-display text-lg font-bold text-white">
          Opening FastAPI Swagger Docs
        </h1>
        <p className="mt-1.5 text-xs leading-relaxed text-slate-400">
          Swagger UI is served by the SearchCore backend at{" "}
          <code className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-slate-200">
            {FASTAPI_DOCS_URL}
          </code>
          .
        </p>
        <div className="mt-5 flex items-center justify-center gap-2.5">
          <Link
            href="/"
            className="inline-flex items-center gap-1.5 rounded-xl border border-slate-700 bg-slate-800/80 px-3.5 py-2 text-xs font-semibold text-slate-200 transition hover:bg-slate-700"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Back to SearchCore
          </Link>
          <a
            href={FASTAPI_DOCS_URL}
            className="inline-flex items-center gap-1.5 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 px-4 py-2 text-xs font-semibold text-white shadow-lg shadow-blue-600/25 transition hover:from-blue-500 hover:to-indigo-500"
          >
            Open Swagger UI
            <ExternalLink className="h-3.5 w-3.5" />
          </a>
        </div>
      </div>
    </main>
  );
}

