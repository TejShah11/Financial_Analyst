"use client";

import { useEffect, useState } from "react";
import { PlusIcon, MessageSquareIcon, Trash2Icon, XIcon, BarChart2Icon, BookOpenIcon, TrendingUpIcon } from "lucide-react";
import clsx from "clsx";
import type { Session } from "@/types";
import { loadSessions, deleteSession, formatRelativeTime } from "@/lib/sessions";

const KNOWLEDGE_BASE = [
  { label: "Q1 FY26 — IFRS USD press release", icon: "📊" },
  { label: "Q2 FY26 — IFRS USD press release", icon: "📊" },
  { label: "Q3 FY26 — IFRS USD press release", icon: "📊" },
  { label: "Q4 FY26 — IFRS USD press release", icon: "📊" },
  { label: "Infosys Annual Report FY25", icon: "📋" },
  { label: "Daily share-price history (CSV)", icon: "📈" },
  { label: "Investor data sheet (XLS)", icon: "📉" },
];

interface SidebarProps {
  currentSessionId: string;
  onNewChat: () => void;
  onSelectSession: (id: string) => void;
  onClose?: () => void;
  isMobileOpen?: boolean;
}

export default function Sidebar({
  currentSessionId,
  onNewChat,
  onSelectSession,
  onClose,
  isMobileOpen,
}: SidebarProps) {
  const [sessions, setSessions] = useState<Session[]>([]);

  useEffect(() => {
    setSessions(loadSessions());
  }, [currentSessionId]);

  const handleDelete = (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    deleteSession(id);
    setSessions(loadSessions());
    if (id === currentSessionId) onNewChat();
  };

  return (
    <>
      {/* Mobile backdrop */}
      {isMobileOpen && (
        <div
          className="fixed inset-0 bg-black/60 backdrop-blur-sm z-20 md:hidden"
          onClick={onClose}
        />
      )}

      <aside
        className={clsx(
          "fixed md:relative z-30 md:z-auto",
          "flex flex-col h-full w-72",
          "transition-transform duration-300 ease-out",
          "md:translate-x-0",
          isMobileOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"
        )}
        style={{ background: "var(--bg-surface)", borderRight: "1px solid var(--border)" }}
      >
        {/* ── Brand header ──────────────────────────────────────── */}
        <div className="flex items-center justify-between px-5 py-5">
          <div className="flex items-center gap-2.5">
            <div
              className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
              style={{ background: "linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%)" }}
            >
              <BarChart2Icon className="w-4 h-4 text-white" />
            </div>
            <div>
              <span className="font-semibold text-sm gradient-text">LedgerMind</span>
              <p className="text-xs" style={{ color: "var(--text-muted)" }}>Financial Intelligence</p>
            </div>
          </div>
          {/* Mobile close */}
          <button
            onClick={onClose}
            className="md:hidden p-1.5 rounded-md hover:bg-white/5 transition-colors"
          >
            <XIcon className="w-4 h-4" style={{ color: "var(--text-secondary)" }} />
          </button>
        </div>

        {/* ── New Chat button ────────────────────────────────────── */}
        <div className="px-3 pb-3">
          <button
            onClick={onNewChat}
            className="w-full flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 group"
            style={{
              background: "linear-gradient(135deg, rgba(59,130,246,0.15) 0%, rgba(139,92,246,0.15) 100%)",
              border: "1px solid rgba(59,130,246,0.25)",
              color: "#93c5fd",
            }}
          >
            <PlusIcon className="w-4 h-4 group-hover:rotate-90 transition-transform duration-200" />
            New conversation
          </button>
        </div>

        {/* ── Session history ────────────────────────────────────── */}
        <div className="flex-1 overflow-y-auto px-3 space-y-0.5 min-h-0">
          {sessions.length > 0 && (
            <>
              <p
                className="px-2 py-1.5 text-xs font-semibold uppercase tracking-wider"
                style={{ color: "var(--text-muted)" }}
              >
                Recent
              </p>
              {sessions.map((s) => (
                <div
                  key={s.id}
                  onClick={() => onSelectSession(s.id)}
                  className={clsx(
                    "group flex items-start gap-2 px-2.5 py-2 rounded-lg cursor-pointer transition-all duration-150",
                    s.id === currentSessionId
                      ? "bg-blue-500/10 border border-blue-500/20"
                      : "hover:bg-white/[0.04] border border-transparent"
                  )}
                >
                  <MessageSquareIcon
                    className="w-3.5 h-3.5 mt-0.5 flex-shrink-0"
                    style={{
                      color: s.id === currentSessionId ? "#60a5fa" : "var(--text-muted)",
                    }}
                  />
                  <div className="flex-1 min-w-0">
                    <p
                      className="text-xs truncate leading-snug"
                      style={{
                        color: s.id === currentSessionId ? "#e2e8f0" : "var(--text-secondary)",
                      }}
                    >
                      {s.title}
                    </p>
                    <p className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
                      {formatRelativeTime(s.createdAt)}
                    </p>
                  </div>
                  <button
                    onClick={(e) => handleDelete(e, s.id)}
                    className="opacity-0 group-hover:opacity-100 p-0.5 rounded transition-opacity"
                  >
                    <Trash2Icon className="w-3 h-3" style={{ color: "var(--text-muted)" }} />
                  </button>
                </div>
              ))}
            </>
          )}
        </div>

        {/* ── Knowledge base ─────────────────────────────────────── */}
        <div
          className="mx-3 mb-3 p-3 rounded-xl"
          style={{ background: "var(--bg-raised)", border: "1px solid var(--border)" }}
        >
          <div className="flex items-center gap-1.5 mb-2.5">
            <BookOpenIcon className="w-3.5 h-3.5" style={{ color: "#60a5fa" }} />
            <span className="text-xs font-semibold" style={{ color: "#93c5fd" }}>
              Knowledge Base
            </span>
          </div>
          <ul className="space-y-1.5">
            {KNOWLEDGE_BASE.map((doc) => (
              <li key={doc.label} className="flex items-start gap-1.5">
                <span className="text-xs mt-0.5 flex-shrink-0">{doc.icon}</span>
                <span className="text-xs leading-snug" style={{ color: "var(--text-muted)" }}>
                  {doc.label}
                </span>
              </li>
            ))}
          </ul>
        </div>

        {/* ── Tips ──────────────────────────────────────────────── */}
        <div className="px-4 pb-4">
          <div className="flex items-center gap-1.5 mb-1">
            <TrendingUpIcon className="w-3 h-3" style={{ color: "var(--text-muted)" }} />
            <span className="text-xs" style={{ color: "var(--text-muted)" }}>
              Say <span className="font-medium" style={{ color: "#94a3b8" }}>"export to Excel"</span> to download data
            </span>
          </div>
        </div>
      </aside>
    </>
  );
}
