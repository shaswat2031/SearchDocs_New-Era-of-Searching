"use client";

import { motion } from "framer-motion";
import {
  Activity,
  BookOpen,
  Cpu,
  FileText,
  Hash,
} from "lucide-react";
import type { StatsResponse } from "@/lib/api";

interface StatsStripProps {
  stats: StatsResponse;
  loading?: boolean;
}

export function StatsStrip({ stats, loading = false }: StatsStripProps) {
  const items = [
    {
      label: "Documents",
      value: stats.total_documents.toLocaleString(),
      icon: FileText,
      accent: "from-blue-500/20 to-indigo-500/5 text-blue-400 border-blue-500/20",
      dot: "bg-blue-400",
    },
    {
      label: "Vocabulary",
      value: stats.vocabulary_size.toLocaleString(),
      icon: BookOpen,
      accent: "from-violet-500/20 to-purple-500/5 text-violet-400 border-violet-500/20",
      dot: "bg-violet-400",
    },
    {
      label: "Total Tokens",
      value: stats.total_tokens.toLocaleString(),
      icon: Hash,
      accent: "from-cyan-500/20 to-sky-500/5 text-cyan-400 border-cyan-500/20",
      dot: "bg-cyan-400",
    },
    {
      label: "Avg Doc Length",
      value: Number.isFinite(stats.avg_doc_length)
        ? stats.avg_doc_length.toFixed(1)
        : "0",
      icon: Activity,
      accent: "from-amber-500/20 to-orange-500/5 text-amber-400 border-amber-500/20",
      dot: "bg-amber-400",
    },
    {
      label: "Parallel Workers",
      value: stats.parallel_active ? `${stats.parallel_workers} active` : "standby",
      icon: Cpu,
      accent: stats.parallel_active
        ? "from-emerald-500/25 to-teal-500/5 text-emerald-400 border-emerald-500/30"
        : "from-slate-500/15 to-slate-500/5 text-slate-400 border-slate-700/60",
      dot: stats.parallel_active ? "bg-emerald-400 animate-pulse" : "bg-slate-500",
    },
  ];

  return (
    <motion.section
      initial="hidden"
      animate="show"
      variants={{
        hidden: {},
        show: {
          transition: { staggerChildren: 0.055 },
        },
      }}
      className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5"
    >
      {items.map((item) => {
        const Icon = item.icon;
        return (
          <motion.div
            key={item.label}
            variants={{
              hidden: { opacity: 0, y: 12 },
              show: {
                opacity: 1,
                y: 0,
                transition: { type: "spring", stiffness: 360, damping: 28 },
              },
            }}
            whileHover={{ y: -2 }}
            className="group relative overflow-hidden rounded-2xl border border-slate-800/90 bg-[#0b1120]/90 p-4 shadow-lg shadow-black/25 backdrop-blur-md transition-colors hover:border-slate-700"
          >
            <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/12 to-transparent" />
            <div className="flex items-center justify-between gap-2">
              <span className="text-[11px] font-semibold uppercase tracking-[0.09em] text-slate-400">
                {item.label}
              </span>
              <span
                className={`flex h-7 w-7 items-center justify-center rounded-lg border bg-gradient-to-br ${item.accent}`}
              >
                <Icon className="h-3.5 w-3.5" />
              </span>
            </div>
            <div className="mt-2.5 flex items-baseline gap-2">
              <span
                className={`font-mono text-2xl font-bold tracking-tight tabular-nums text-slate-100 ${
                  loading ? "opacity-60" : ""
                }`}
              >
                {item.value}
              </span>
              <span className={`h-1.5 w-1.5 rounded-full ${item.dot}`} />
            </div>
          </motion.div>
        );
      })}
    </motion.section>
  );
}

