"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

type Msg = { role: "user" | "assistant"; content: string };

const STARTERS = [
  "What does Agentry build?",
  "Would AI agents work for my business?",
  "How do we get started?",
];

// Render bare URLs and known internal paths as links inside a plain-text reply.
const LINK_RE =
  /(https?:\/\/[^\s]+|\/(?:audit|roi-calculator|roast|tools|writing|blog|ai-agents-for)(?:\/[\w-]+)*)/g;

function Linkified({ text }: { text: string }) {
  const parts = text.split(LINK_RE);
  return (
    <>
      {parts.map((p, i) =>
        p && p.match(LINK_RE) ? (
          <a
            key={i}
            href={p}
            target={p.startsWith("http") ? "_blank" : undefined}
            rel="noreferrer"
            className="text-sky-400 underline underline-offset-2 hover:text-sky-300"
          >
            {p}
          </a>
        ) : (
          <span key={i}>{p}</span>
        ),
      )}
    </>
  );
}

export function ConciergeChat() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const sessionRef = useRef<string>("");

  useEffect(() => {
    let sid = sessionStorage.getItem("agentry_chat_sid");
    if (!sid) {
      sid = crypto.randomUUID();
      sessionStorage.setItem("agentry_chat_sid", sid);
    }
    sessionRef.current = sid;
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy, open]);

  async function send(text: string) {
    const content = text.trim();
    if (!content || busy) return;
    setError(null);
    const next: Msg[] = [...messages, { role: "user", content }];
    setMessages(next);
    setInput("");
    setBusy(true);
    try {
      const res = await fetch("/api/concierge", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionRef.current,
          page: pathname,
          messages: next.slice(-16),
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.reply) throw new Error(data.error || "failed");
      setMessages([...next, { role: "assistant", content: String(data.reply) }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something glitched — try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      {/* Launcher */}
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-label={open ? "Close chat" : "Chat with Agentry"}
        className="fixed bottom-5 right-5 z-50 flex h-13 w-13 items-center justify-center rounded-full bg-sky-400 p-3.5 text-neutral-950 shadow-lg shadow-sky-950/40 transition-transform hover:scale-105"
      >
        {open ? (
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden>
            <path d="M5 5l10 10M15 5L5 15" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
        ) : (
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden>
            <path
              d="M21 11.5a8.38 8.38 0 01-.9 3.8 8.5 8.5 0 01-7.6 4.7 8.38 8.38 0 01-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 01-.9-3.8 8.5 8.5 0 014.7-7.6 8.38 8.38 0 013.8-.9h.5a8.48 8.48 0 018 8v.5z"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        )}
      </button>

      {/* Panel */}
      {open && (
        <div className="fixed bottom-20 right-5 z-50 flex h-[min(560px,calc(100dvh-7rem))] w-[min(380px,calc(100vw-2.5rem))] flex-col overflow-hidden rounded-2xl border border-neutral-800 bg-neutral-950 shadow-2xl shadow-black/50">
          <div className="flex items-center gap-2 border-b border-neutral-800 px-4 py-3">
            <span className="h-2 w-2 rounded-full bg-sky-400" />
            <div>
              <div className="text-sm font-semibold text-white">Ask Agentry</div>
              <div className="text-[11px] text-neutral-500">
                An agent we built — answers about what we&apos;d build for you
              </div>
            </div>
          </div>

          <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
            {messages.length === 0 && (
              <div className="space-y-2">
                <p className="text-[13px] leading-relaxed text-neutral-400">
                  Hey — ask anything about AI agents for your business, or start with one of these:
                </p>
                {STARTERS.map((s) => (
                  <button
                    key={s}
                    onClick={() => send(s)}
                    className="block w-full rounded-xl border border-neutral-800 bg-neutral-900/60 px-3 py-2 text-left text-[13px] text-neutral-300 transition-colors hover:border-neutral-600"
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
                <div
                  className={
                    m.role === "user"
                      ? "max-w-[85%] rounded-2xl rounded-br-sm bg-sky-400 px-3.5 py-2 text-[13px] leading-relaxed text-neutral-950"
                      : "max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-bl-sm border border-neutral-800 bg-neutral-900 px-3.5 py-2 text-[13px] leading-relaxed text-neutral-200"
                  }
                >
                  {m.role === "assistant" ? <Linkified text={m.content} /> : m.content}
                </div>
              </div>
            ))}
            {busy && (
              <div className="flex justify-start">
                <div className="rounded-2xl rounded-bl-sm border border-neutral-800 bg-neutral-900 px-4 py-2.5 text-neutral-400">
                  <span className="inline-flex gap-1">
                    <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-neutral-500 [animation-delay:0ms]" />
                    <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-neutral-500 [animation-delay:120ms]" />
                    <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-neutral-500 [animation-delay:240ms]" />
                  </span>
                </div>
              </div>
            )}
            {error && <p className="text-center text-[12px] text-red-400">{error}</p>}
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              send(input);
            }}
            className="flex items-center gap-2 border-t border-neutral-800 p-3"
          >
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Type a message…"
              maxLength={1200}
              className="min-w-0 flex-1 rounded-full border border-neutral-700 bg-neutral-900 px-4 py-2 text-[13px] text-neutral-100 placeholder:text-neutral-600 focus:border-sky-500 focus:outline-none"
            />
            <button
              type="submit"
              disabled={busy || !input.trim()}
              aria-label="Send"
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-sky-400 text-neutral-950 transition-colors hover:bg-sky-300 disabled:opacity-40"
            >
              <svg width="16" height="16" viewBox="0 0 20 20" fill="none" aria-hidden>
                <path d="M3 10h13M11 5l5 5-5 5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          </form>
        </div>
      )}
    </>
  );
}
