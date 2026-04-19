import type { CitationSource } from "@/lib/games";

export function getApiBase(): string {
  const raw = import.meta.env.VITE_API_BASE_URL;
  if (raw !== undefined && raw !== null && String(raw).trim() !== "") {
    return String(raw).replace(/\/$/, "");
  }
  // Dev: default to Vite proxy (vite.config.ts) so the browser uses same-origin /api → :8000.
  if (import.meta.env.DEV) {
    return "/api";
  }
  return "";
}

function networkHelp(): string {
  return (
    "Cannot reach the SpielBot API. Start it in a separate terminal from the repo root: " +
    "uvicorn api.main:app --host 127.0.0.1 --port 8000. " +
    "For local dev, use VITE_API_BASE_URL=/api in frontend/.env (see frontend/.env.example) " +
    "so Vite proxies to the API, then restart npm run dev."
  );
}

/** Turns bare TypeError from fetch into a clearer message. */
function rethrowNetworkError(e: unknown): never {
  if (e instanceof TypeError) {
    const m = String((e as Error).message || "");
    if (m === "Failed to fetch" || m.toLowerCase().includes("fetch") || m.toLowerCase().includes("network")) {
      throw new ApiError(networkHelp(), 0);
    }
  }
  throw e;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function createSession(game: string): Promise<{ session_id: string }> {
  const base = getApiBase();
  if (!base) throw new ApiError("VITE_API_BASE_URL is not set", 0);
  let r: Response;
  try {
    r = await fetch(`${base}/v1/sessions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ game }),
    });
  } catch (e) {
    rethrowNetworkError(e);
  }
  if (!r.ok) {
    const t = await r.text();
    throw new ApiError(t || r.statusText, r.status);
  }
  return r.json() as Promise<{ session_id: string }>;
}

export async function deleteSession(sessionId: string): Promise<void> {
  const base = getApiBase();
  if (!base) return;
  try {
    await fetch(`${base}/v1/sessions/${encodeURIComponent(sessionId)}`, {
      method: "DELETE",
    });
  } catch {
    /* best-effort */
  }
}

export type ChatDonePayload = {
  answer: string;
  sources: CitationSource[];
  sub_questions: string[];
  error: string | null;
  latency_ms: number;
};

/** Non-streaming chat (POST /v1/chat). */
export async function sendChat(params: {
  sessionId: string;
  message: string;
  imageBase64?: string | null;
}): Promise<ChatDonePayload> {
  const base = getApiBase();
  if (!base) throw new ApiError("VITE_API_BASE_URL is not set", 0);
  let r: Response;
  try {
    r = await fetch(`${base}/v1/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: params.sessionId,
        message: params.message,
        image_base64: params.imageBase64 ?? null,
      }),
    });
  } catch (e) {
    rethrowNetworkError(e);
  }
  if (!r.ok) {
    const t = await r.text();
    throw new ApiError(t || r.statusText, r.status);
  }
  const data = (await r.json()) as {
    answer: string;
    sources: CitationSource[];
    sub_questions: string[];
    error: string | null;
    latency_ms: number;
  };
  return {
    answer: data.answer,
    sources: data.sources ?? [],
    sub_questions: data.sub_questions ?? [],
    error: data.error,
    latency_ms: data.latency_ms,
  };
}

/**
 * Streaming chat (SSE). Invokes onToken for each chunk; resolves with final payload.
 */
export async function streamChat(
  params: {
    sessionId: string;
    message: string;
    imageBase64?: string | null;
  },
  onToken: (text: string) => void,
): Promise<ChatDonePayload> {
  const base = getApiBase();
  if (!base) throw new ApiError("VITE_API_BASE_URL is not set", 0);

  let r: Response;
  try {
    r = await fetch(`${base}/v1/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: params.sessionId,
        message: params.message,
        image_base64: params.imageBase64 ?? null,
      }),
    });
  } catch (e) {
    rethrowNetworkError(e);
  }

  if (!r.ok) {
    const t = await r.text();
    throw new ApiError(t || r.statusText, r.status);
  }

  const reader = r.body?.getReader();
  if (!reader) {
    throw new ApiError("No response body", r.status);
  }

  const decoder = new TextDecoder();
  let buffer = "";

  const handleEvent = (ev: { type: string; [k: string]: unknown }): ChatDonePayload | null => {
    if (ev.type === "token" && typeof ev.text === "string") {
      onToken(ev.text);
      return null;
    }
    if (ev.type === "error" && typeof ev.message === "string") {
      throw new ApiError(ev.message);
    }
    if (ev.type === "done") {
      return {
        answer: typeof ev.answer === "string" ? ev.answer : "",
        sources: Array.isArray(ev.sources) ? (ev.sources as CitationSource[]) : [],
        sub_questions: Array.isArray(ev.sub_questions) ? (ev.sub_questions as string[]) : [],
        error: typeof ev.error === "string" ? ev.error : null,
        latency_ms: typeof ev.latency_ms === "number" ? ev.latency_ms : 0,
      };
    }
    return null;
  };

  const parseOneBlock = (block: string): { type: string; [k: string]: unknown } | null => {
    const line = block
      .split("\n")
      .map((l) => l.trimEnd())
      .find((l) => l.startsWith("data:"));
    if (!line) return null;
    const json = line.replace(/^data:\s*/, "").trim();
    if (!json) return null;
    try {
      return JSON.parse(json) as { type: string; [k: string]: unknown };
    } catch {
      return null;
    }
  };

  let donePayload: ChatDonePayload | null = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      const ev = parseOneBlock(block);
      if (!ev) continue;
      const result = handleEvent(ev);
      if (result) donePayload = result;
    }
  }

  if (buffer.trim()) {
    const ev = parseOneBlock(buffer);
    if (ev) {
      const result = handleEvent(ev);
      if (result) donePayload = result;
    }
  }

  if (!donePayload) {
    throw new ApiError("Stream ended without done event");
  }

  return donePayload;
}
