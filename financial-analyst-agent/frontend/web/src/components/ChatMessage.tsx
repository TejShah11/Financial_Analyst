"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { BarChart2Icon, DownloadIcon, FileTextIcon, FileSpreadsheetIcon, ShieldCheckIcon, UserIcon } from "lucide-react";
import clsx from "clsx";
import type { Message } from "@/types";

interface ChatMessageProps {
  message: Message;
}

function TypingIndicator() {
  return (
    <div className="flex items-center gap-1 px-1 py-2">
      <span className="typing-dot" />
      <span className="typing-dot" />
      <span className="typing-dot" />
    </div>
  );
}

function SourceBadge({ source }: { source: string }) {
  const name = source.replace(/\.pdf$|\.csv$|\.xls$|\.xlsx$/i, "");
  const ext = source.match(/\.(pdf|csv|xls|xlsx)$/i)?.[1]?.toLowerCase() ?? "";

  const colors: Record<string, string> = {
    pdf: "rgba(239,68,68,0.15)",
    csv: "rgba(34,197,94,0.15)",
    xls: "rgba(59,130,246,0.15)",
    xlsx: "rgba(59,130,246,0.15)",
  };
  const textColors: Record<string, string> = {
    pdf: "#fca5a5",
    csv: "#86efac",
    xls: "#93c5fd",
    xlsx: "#93c5fd",
  };

  return (
    <span
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs"
      style={{
        background: colors[ext] ?? "rgba(148,163,184,0.1)",
        color: textColors[ext] ?? "#94a3b8",
        border: `1px solid ${textColors[ext] ? textColors[ext] + "30" : "rgba(148,163,184,0.15)"}`,
      }}
    >
      <FileTextIcon className="w-3 h-3 flex-shrink-0" />
      <span className="max-w-[160px] truncate">{name}</span>
    </span>
  );
}

function DownloadButton({ fileUrl }: { fileUrl: string }) {
  const filename = fileUrl.split("/").pop() ?? "file";
  const isExcel = filename.endsWith(".xlsx");

  return (
    <a
      href={fileUrl}
      download={filename}
      className="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg text-sm font-medium transition-all duration-200 hover:scale-[1.02] active:scale-[0.98]"
      style={{
        background: isExcel
          ? "linear-gradient(135deg, rgba(34,197,94,0.2) 0%, rgba(16,185,129,0.2) 100%)"
          : "linear-gradient(135deg, rgba(239,68,68,0.2) 0%, rgba(220,38,38,0.2) 100%)",
        border: isExcel ? "1px solid rgba(34,197,94,0.3)" : "1px solid rgba(239,68,68,0.3)",
        color: isExcel ? "#86efac" : "#fca5a5",
      }}
    >
      {isExcel ? (
        <FileSpreadsheetIcon className="w-4 h-4" />
      ) : (
        <DownloadIcon className="w-4 h-4" />
      )}
      {isExcel ? "Download Excel" : "Download PDF"}
      <span
        className="text-xs px-1.5 py-0.5 rounded font-mono"
        style={{ background: "rgba(255,255,255,0.08)", color: "inherit" }}
      >
        {isExcel ? "XLSX" : "PDF"}
      </span>
    </a>
  );
}

export default function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div className="flex justify-end gap-3 animate-slide-up">
        <div
          className="max-w-[75%] px-4 py-3 rounded-2xl rounded-tr-sm text-sm leading-relaxed"
          style={{
            background: "linear-gradient(135deg, #1e3a5f 0%, #1e2d52 100%)",
            border: "1px solid rgba(96,165,250,0.2)",
            color: "#e2e8f0",
          }}
        >
          {message.content}
        </div>
        <div
          className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5"
          style={{ background: "rgba(96,165,250,0.15)", border: "1px solid rgba(96,165,250,0.2)" }}
        >
          <UserIcon className="w-4 h-4" style={{ color: "#60a5fa" }} />
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-3 animate-slide-up">
      {/* Avatar */}
      <div
        className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5"
        style={{
          background: "linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%)",
          boxShadow: "0 0 12px rgba(59,130,246,0.25)",
        }}
      >
        <BarChart2Icon className="w-4 h-4 text-white" />
      </div>

      {/* Bubble */}
      <div className="flex-1 min-w-0 max-w-[85%]">
        <div
          className="px-4 py-3 rounded-2xl rounded-tl-sm"
          style={{
            background: "var(--bg-raised)",
            border: "1px solid var(--border-md)",
          }}
        >
          {/* Streaming indicator */}
          {message.isStreaming && !message.content && <TypingIndicator />}

          {/* Message content */}
          {message.content && (
            <div className="message-prose text-sm">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  table: ({ children }) => (
                    <div className="overflow-x-auto my-3 rounded-lg" style={{ border: "1px solid rgba(255,255,255,0.08)" }}>
                      <table className="w-full">{children}</table>
                    </div>
                  ),
                  thead: ({ children }) => (
                    <thead style={{ background: "rgba(59,130,246,0.08)" }}>{children}</thead>
                  ),
                  th: ({ children }) => (
                    <th className="px-3 py-2 text-left text-xs font-semibold" style={{ color: "#93c5fd", borderBottom: "1px solid rgba(59,130,246,0.2)" }}>
                      {children}
                    </th>
                  ),
                  td: ({ children }) => (
                    <td className="px-3 py-2 text-xs" style={{ color: "#cbd5e1", borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
                      {children}
                    </td>
                  ),
                  code: ({ children, className }) => {
                    const isBlock = className?.includes("language-");
                    return isBlock ? (
                      <code className={clsx("block text-xs font-mono p-3 rounded-lg overflow-x-auto", className)} style={{ background: "var(--bg-surface)", color: "#c4b5fd" }}>
                        {children}
                      </code>
                    ) : (
                      <code className="text-xs font-mono px-1.5 py-0.5 rounded" style={{ background: "rgba(139,92,246,0.15)", color: "#c4b5fd" }}>
                        {children}
                      </code>
                    );
                  },
                  strong: ({ children }) => (
                    <strong style={{ color: "#e2e8f0", fontWeight: 600 }}>{children}</strong>
                  ),
                  a: ({ children, href }) => (
                    <a href={href} className="underline hover:no-underline" style={{ color: "#60a5fa" }} target="_blank" rel="noopener noreferrer">
                      {children}
                    </a>
                  ),
                  blockquote: ({ children }) => (
                    <blockquote className="pl-3 py-0.5 my-2 italic text-sm" style={{ borderLeft: "3px solid rgba(96,165,250,0.4)", color: "#94a3b8" }}>
                      {children}
                    </blockquote>
                  ),
                }}
              >
                {message.content}
              </ReactMarkdown>
            </div>
          )}
        </div>

        {/* Footer: verified badge + sources + download */}
        {!message.isStreaming && message.content && (
          <div className="mt-2 flex flex-wrap items-center gap-2">
            {message.verified && (
              <span
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs"
                style={{ background: "rgba(34,197,94,0.1)", color: "#86efac", border: "1px solid rgba(34,197,94,0.2)" }}
              >
                <ShieldCheckIcon className="w-3 h-3" />
                Verified
              </span>
            )}

            {message.sources && message.sources.length > 0 &&
              message.sources.map((s) => <SourceBadge key={s} source={s} />)}

            {message.fileUrl && <DownloadButton fileUrl={message.fileUrl} />}
          </div>
        )}
      </div>
    </div>
  );
}
