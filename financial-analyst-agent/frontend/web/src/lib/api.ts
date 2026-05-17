import type { StreamEvent, Message } from "@/types";

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

export const BACKEND_URL = BACKEND;

export async function* streamChat(
  query: string,
  sessionId: string
): AsyncGenerator<StreamEvent, void, unknown> {
  const res = await fetch(`${BACKEND}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, session_id: sessionId }),
  });

  if (!res.ok) {
    throw new Error(`Backend responded ${res.status}: ${res.statusText}`);
  }

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed) {
        try {
          yield JSON.parse(trimmed) as StreamEvent;
        } catch {
          // skip malformed lines
        }
      }
    }
  }

  if (buffer.trim()) {
    try {
      yield JSON.parse(buffer.trim()) as StreamEvent;
    } catch {
      // ignore
    }
  }
}

export async function fetchHistory(sessionId: string): Promise<Message[]> {
  try {
    const res = await fetch(`${BACKEND}/history/${sessionId}`);
    if (!res.ok) return [];
    const data = await res.json();
    const raw: Array<{ role: string; content: string }> = data.messages ?? [];
    return raw.map((m, i) => ({
      id: `hist-${i}`,
      role: m.role as "user" | "assistant",
      content: m.content,
    }));
  } catch {
    return [];
  }
}
