"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  KeyboardEvent,
} from "react";
import { v4 as uuid } from "uuid";
import {
  SendIcon,
  MenuIcon,
  WifiIcon,
  WifiOffIcon,
  StopCircleIcon,
  SparklesIcon,
} from "lucide-react";
import clsx from "clsx";

import Sidebar from "@/components/Sidebar";
import ChatMessage from "@/components/ChatMessage";
import ProgressIndicator from "@/components/ProgressIndicator";
import { streamChat, fetchHistory, BACKEND_URL } from "@/lib/api";
import { loadSessions, saveSession } from "@/lib/sessions";
import type { Message, ProgressStep } from "@/types";

const WELCOME: Message = {
  id: "welcome",
  role: "assistant",
  content:
    "Hello! I'm **LedgerMind**, your Infosys FY26 financial intelligence agent.\n\n" +
    "Ask me about quarterly results, operating margins, large deal TCV, free cash flow, " +
    "share-price data, or the full-year annual report — I remember follow-up questions " +
    "and can export every answer to **PDF or Excel**.",
  verified: false,
};

const SUGGESTIONS = [
  "What was Infosys's revenue in Q1 FY26?",
  "Compare operating margins across all four quarters",
  "What was the large deal TCV in Q3 FY26?",
  "What is the FY27 guidance for revenue growth?",
];

/* ── Health check ──────────────────────────────────────────────── */
async function checkBackend(): Promise<boolean> {
  try {
    const r = await fetch(`${BACKEND_URL}/health`, { signal: AbortSignal.timeout(3000) });
    return r.ok;
  } catch {
    return false;
  }
}

/* ── Session helpers ────────────────────────────────────────────── */
function getOrCreateSessionId(): string {
  if (typeof window === "undefined") return uuid();
  const params = new URLSearchParams(window.location.search);
  const fromUrl = params.get("session");
  if (fromUrl) return fromUrl;
  const fresh = uuid();
  params.set("session", fresh);
  window.history.replaceState(null, "", `?${params.toString()}`);
  return fresh;
}

function setSessionInUrl(id: string) {
  if (typeof window === "undefined") return;
  const params = new URLSearchParams(window.location.search);
  params.set("session", id);
  window.history.replaceState(null, "", `?${params.toString()}`);
}

export default function ChatInterface() {
  const [sessionId, setSessionId] = useState<string>("");
  const [messages, setMessages] = useState<Message[]>([WELCOME]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [steps, setSteps] = useState<ProgressStep[]>([]);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [isOnline, setIsOnline] = useState<boolean | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  /* ── Initialise session on mount ───────────────────────────── */
  useEffect(() => {
    const id = getOrCreateSessionId();
    setSessionId(id);
    checkBackend().then(setIsOnline);

    // Restore history if session already exists
    fetchHistory(id).then((hist) => {
      if (hist.length > 0) setMessages([WELCOME, ...hist]);
    });
  }, []);

  /* ── Health check every 30 s ───────────────────────────────── */
  useEffect(() => {
    const interval = setInterval(() => checkBackend().then(setIsOnline), 30_000);
    return () => clearInterval(interval);
  }, []);

  /* ── Auto-scroll ───────────────────────────────────────────── */
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, steps]);

  /* ── Auto-resize textarea ──────────────────────────────────── */
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [input]);

  /* ── New chat ──────────────────────────────────────────────── */
  const startNewChat = useCallback(() => {
    const id = uuid();
    setSessionId(id);
    setSessionInUrl(id);
    setMessages([WELCOME]);
    setSteps([]);
    setInput("");
    setIsSidebarOpen(false);
  }, []);

  /* ── Select existing session ────────────────────────────────── */
  const selectSession = useCallback(async (id: string) => {
    setSessionId(id);
    setSessionInUrl(id);
    setMessages([WELCOME]);
    setSteps([]);
    setIsSidebarOpen(false);
    const hist = await fetchHistory(id);
    if (hist.length > 0) setMessages([WELCOME, ...hist]);
  }, []);

  /* ── Send message ───────────────────────────────────────────── */
  const sendMessage = useCallback(
    async (text: string) => {
      if (!text.trim() || isLoading) return;
      setInput("");

      const userMsg: Message = { id: uuid(), role: "user", content: text.trim() };
      const assistantId = uuid();
      const placeholder: Message = {
        id: assistantId,
        role: "assistant",
        content: "",
        isStreaming: true,
      };

      setMessages((prev) => [...prev, userMsg, placeholder]);
      setSteps([]);
      setIsLoading(true);

      const ac = new AbortController();
      abortRef.current = ac;

      try {
        const gen = streamChat(text.trim(), sessionId);

        for await (const event of gen) {
          if (ac.signal.aborted) break;

          if (event.type === "progress") {
            setSteps((prev) => [
              ...prev.map((s) => ({ ...s, done: true })),
              { node: event.node, label: event.label, done: false },
            ]);
          } else if (event.type === "result") {
            const fileUrl = event.file_url
              ? `${BACKEND_URL}${event.file_url}`
              : undefined;

            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? {
                      ...m,
                      content: event.answer,
                      sources: event.sources,
                      fileUrl,
                      verified: event.verified,
                      intent: event.intent,
                      isStreaming: false,
                    }
                  : m
              )
            );
            setSteps([]);

            // Persist session in localStorage
            const allMessages = [...messages, userMsg];
            const title = text.trim().slice(0, 48) + (text.length > 48 ? "…" : "");
            saveSession({
              id: sessionId,
              title,
              createdAt: Date.now(),
              messageCount: allMessages.length,
            });
          } else if (event.type === "error") {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? {
                      ...m,
                      content: `**Error:** ${event.detail}`,
                      isStreaming: false,
                      isError: true,
                    }
                  : m
              )
            );
            setSteps([]);
          }
        }
      } catch (err: unknown) {
        if (ac.signal.aborted) {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? { ...m, content: "_Response stopped._", isStreaming: false }
                : m
            )
          );
        } else {
          const detail =
            err instanceof Error ? err.message : "Could not reach the backend.";
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? {
                    ...m,
                    content: `**Backend unreachable.** ${detail}\n\nMake sure the FastAPI server is running at \`http://localhost:8000\`.`,
                    isStreaming: false,
                    isError: true,
                  }
                : m
            )
          );
        }
        setSteps([]);
      } finally {
        setIsLoading(false);
        abortRef.current = null;
        inputRef.current?.focus();
      }
    },
    [isLoading, sessionId, messages]
  );

  /* ── Stop generation ───────────────────────────────────────── */
  const stopGeneration = () => {
    abortRef.current?.abort();
  };

  /* ── Keyboard handler ───────────────────────────────────────── */
  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  };

  const showEmptyState = messages.length === 1 && messages[0].id === "welcome";

  return (
    <div className="flex h-full" style={{ background: "var(--bg-base)" }}>
      {/* ── Sidebar ─────────────────────────────────────────── */}
      <Sidebar
        currentSessionId={sessionId}
        onNewChat={startNewChat}
        onSelectSession={selectSession}
        onClose={() => setIsSidebarOpen(false)}
        isMobileOpen={isSidebarOpen}
      />

      {/* ── Main area ───────────────────────────────────────── */}
      <div className="flex flex-col flex-1 min-w-0">
        {/* ── Top bar ────────────────────────────────────────── */}
        <header
          className="flex items-center gap-3 px-4 py-3 flex-shrink-0"
          style={{ borderBottom: "1px solid var(--border)", background: "var(--bg-surface)" }}
        >
          {/* Mobile hamburger */}
          <button
            onClick={() => setIsSidebarOpen(true)}
            className="md:hidden p-1.5 rounded-lg hover:bg-white/5 transition-colors"
          >
            <MenuIcon className="w-5 h-5" style={{ color: "var(--text-secondary)" }} />
          </button>

          <div className="flex-1 min-w-0">
            <h1 className="text-sm font-semibold gradient-text">LedgerMind</h1>
            <p className="text-xs" style={{ color: "var(--text-muted)" }}>
              Infosys FY26 — Quarterly results · Annual report · Share price
            </p>
          </div>

          {/* Connection status */}
          <div className="flex items-center gap-1.5">
            {isOnline === null ? (
              <div className="w-1.5 h-1.5 rounded-full bg-yellow-400/60 animate-pulse" />
            ) : isOnline ? (
              <>
                <WifiIcon className="w-3.5 h-3.5" style={{ color: "#86efac" }} />
                <span className="text-xs hidden sm:inline" style={{ color: "#86efac" }}>
                  Connected
                </span>
              </>
            ) : (
              <>
                <WifiOffIcon className="w-3.5 h-3.5 text-red-400" />
                <span className="text-xs hidden sm:inline text-red-400">Offline</span>
              </>
            )}
          </div>
        </header>

        {/* ── Messages ────────────────────────────────────────── */}
        <div className="flex-1 overflow-y-auto">
          {showEmptyState ? (
            /* ── Welcome / empty state ─────────────────────── */
            <div className="flex flex-col items-center justify-center h-full px-6 pb-8">
              {/* Logo glow */}
              <div className="relative mb-6">
                <div
                  className="absolute inset-0 rounded-full blur-2xl opacity-40"
                  style={{ background: "linear-gradient(135deg, #3b82f6, #8b5cf6)", transform: "scale(1.5)" }}
                />
                <div
                  className="relative w-16 h-16 rounded-2xl flex items-center justify-center"
                  style={{ background: "linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%)" }}
                >
                  <SparklesIcon className="w-8 h-8 text-white" />
                </div>
              </div>

              <h2 className="text-2xl font-bold gradient-text mb-2">LedgerMind</h2>
              <p className="text-sm text-center max-w-md mb-8" style={{ color: "var(--text-secondary)" }}>
                Your agentic financial analyst for Infosys FY26 — powered by LangGraph and Google Gemini.
                Ask about earnings, margins, deals, or share price.
              </p>

              {/* Suggestion chips */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 w-full max-w-lg">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => sendMessage(s)}
                    className="text-left px-4 py-3 rounded-xl text-sm transition-all duration-200 hover:scale-[1.01] active:scale-[0.99]"
                    style={{
                      background: "var(--bg-raised)",
                      border: "1px solid var(--border-md)",
                      color: "var(--text-secondary)",
                    }}
                  >
                    <span className="mr-1.5">💬</span>{s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            /* ── Chat messages ──────────────────────────────── */
            <div className="max-w-3xl mx-auto px-4 py-6 space-y-5">
              {messages.map((msg) => (
                <ChatMessage key={msg.id} message={msg} />
              ))}

              {/* Streaming progress */}
              <ProgressIndicator steps={steps} visible={isLoading} />

              <div ref={bottomRef} />
            </div>
          )}
        </div>

        {/* ── Input area ──────────────────────────────────────── */}
        <div
          className="flex-shrink-0 px-4 pb-4 pt-3"
          style={{ borderTop: "1px solid var(--border)", background: "var(--bg-surface)" }}
        >
          <div className="max-w-3xl mx-auto">
            <div
              className="flex items-end gap-2 p-2 rounded-2xl transition-all duration-200"
              style={{
                background: "var(--bg-raised)",
                border: isLoading
                  ? "1px solid rgba(59,130,246,0.4)"
                  : "1px solid var(--border-md)",
                boxShadow: isLoading ? "0 0 16px rgba(59,130,246,0.1)" : "none",
              }}
            >
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={isLoading}
                rows={1}
                placeholder={
                  isLoading
                    ? "Analysing financial data…"
                    : "Ask about Infosys financials… (Shift+Enter for new line)"
                }
                className="flex-1 bg-transparent resize-none outline-none text-sm leading-relaxed py-1.5 px-1"
                style={{
                  color: "var(--text-primary)",
                  caretColor: "#60a5fa",
                }}
              />

              {isLoading ? (
                <button
                  onClick={stopGeneration}
                  title="Stop generation"
                  className="flex-shrink-0 w-9 h-9 rounded-xl flex items-center justify-center transition-all duration-200 hover:bg-red-500/20"
                  style={{ border: "1px solid rgba(239,68,68,0.3)" }}
                >
                  <StopCircleIcon className="w-4 h-4 text-red-400" />
                </button>
              ) : (
                <button
                  onClick={() => sendMessage(input)}
                  disabled={!input.trim()}
                  title="Send (Enter)"
                  className={clsx(
                    "flex-shrink-0 w-9 h-9 rounded-xl flex items-center justify-center transition-all duration-200",
                    input.trim()
                      ? "hover:scale-105 active:scale-95"
                      : "opacity-30 cursor-not-allowed"
                  )}
                  style={{
                    background: input.trim()
                      ? "linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%)"
                      : "var(--bg-overlay)",
                  }}
                >
                  <SendIcon className="w-4 h-4 text-white" />
                </button>
              )}
            </div>

            <p className="text-xs text-center mt-2" style={{ color: "var(--text-muted)" }}>
              LedgerMind is scoped to Infosys FY26 documents. Answers are grounded in source data only.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
