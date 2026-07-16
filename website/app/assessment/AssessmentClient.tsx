"use client";

import { useEffect, useRef, useState } from "react";

const INPUT =
  "w-full rounded-xl border border-neutral-800 bg-neutral-950 px-4 py-3 text-[15px] text-white placeholder-neutral-600 outline-none transition focus:border-sky-500";
const PRIMARY =
  "inline-flex items-center justify-center gap-2 rounded-full bg-sky-400 px-6 py-3 text-sm font-semibold text-neutral-950 transition hover:bg-sky-300 disabled:cursor-not-allowed disabled:opacity-50";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
const BOOTSTRAP = "I'm ready to start the assessment.";

type Msg = { role: "user" | "assistant"; content: string };
type Preview = {
  status: string;
  company_summary?: string;
  preview?: Array<{ name: string; blurb: string }>;
  quick_wins?: string[];
  total_processes?: number;
};

function sid(): string {
  try {
    const k = "agentry_assessment_sid";
    let v = sessionStorage.getItem(k);
    if (!v) {
      v = `as-${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`;
      sessionStorage.setItem(k, v);
    }
    return v;
  } catch {
    return `as-${Math.random().toString(36).slice(2)}`;
  }
}

export function AssessmentClient({ calUrl }: { calUrl: string }) {
  const [stage, setStage] = useState<"intro" | "chat" | "compiling" | "done" | "error">("intro");
  const [name, setName] = useState("");
  const [company, setCompany] = useState("");
  const [website, setWebsite] = useState("");
  const [email, setEmail] = useState("");
  const [formErr, setFormErr] = useState<string | null>(null);

  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<Preview | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [messages, stage]);

  useEffect(() => () => {
    if (pollRef.current) clearInterval(pollRef.current);
  }, []);

  async function turn(history: Msg[]): Promise<{ reply?: string; done?: boolean; error?: string }> {
    const res = await fetch("/api/assessment", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sid(),
        contact: { name, company, website, email },
        messages: history,
      }),
    });
    return res.json().catch(() => ({ error: "network" }));
  }

  function startPolling() {
    let tries = 0;
    pollRef.current = setInterval(async () => {
      tries += 1;
      if (tries > 30) {
        if (pollRef.current) clearInterval(pollRef.current);
        setStage("error");
        return;
      }
      try {
        const res = await fetch(`/api/assessment/result?session_id=${encodeURIComponent(sid())}`);
        const data = (await res.json()) as Preview;
        if (data.status === "synthesized") {
          if (pollRef.current) clearInterval(pollRef.current);
          setResult(data);
          setStage("done");
        } else if (data.status === "failed") {
          if (pollRef.current) clearInterval(pollRef.current);
          setStage("error");
        }
      } catch {
        // keep polling
      }
    }, 5000);
  }

  async function start() {
    if (!name.trim() || !EMAIL_RE.test(email.trim())) {
      setFormErr("Your name and a work email get the map to you.");
      return;
    }
    setFormErr(null);
    setSending(true);
    setStage("chat");
    const history: Msg[] = [{ role: "user", content: BOOTSTRAP }];
    const out = await turn(history);
    setSending(false);
    if (out.error || !out.reply) {
      setStage("error");
      return;
    }
    setMessages([...history, { role: "assistant", content: out.reply }]);
  }

  async function send() {
    const text = input.trim();
    if (!text || sending) return;
    setInput("");
    const history: Msg[] = [...messages, { role: "user", content: text }];
    setMessages(history);
    setSending(true);
    const out = await turn(history);
    setSending(false);
    if (out.error || !out.reply) {
      setMessages([
        ...history,
        { role: "assistant", content: "sorry, I glitched. mind sending that again?" },
      ]);
      return;
    }
    setMessages([...history, { role: "assistant", content: out.reply }]);
    if (out.done) {
      setStage("compiling");
      startPolling();
    }
  }

  if (stage === "intro") {
    return (
      <div className="rounded-2xl border border-neutral-800 bg-neutral-950 p-6 sm:p-8">
        <div className="grid gap-3 sm:grid-cols-2">
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Your name" className={INPUT} />
          <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Work email" type="email" className={INPUT} />
          <input value={company} onChange={(e) => setCompany(e.target.value)} placeholder="Company (optional)" className={INPUT} />
          <input value={website} onChange={(e) => setWebsite(e.target.value)} placeholder="Website (optional)" className={INPUT} />
        </div>
        {formErr && <p className="mt-3 text-sm text-red-400">{formErr}</p>}
        <button onClick={start} disabled={sending} className={`${PRIMARY} mt-5`}>
          Start the interview →
        </button>
        <p className="mt-3 text-xs text-neutral-500">
          10-15 questions, about 10 minutes. Your top opportunities appear instantly at the end.
        </p>
      </div>
    );
  }

  if (stage === "done" && result) {
    return (
      <div className="rounded-2xl border border-sky-900/50 bg-neutral-950 p-6 sm:p-8">
        <p className="text-xs font-semibold uppercase tracking-wider text-sky-400">Your preview — top 3 of {result.total_processes ?? "?"} mapped</p>
        {result.company_summary && (
          <p className="mt-3 text-[15px] leading-relaxed text-neutral-300">{result.company_summary}</p>
        )}
        <div className="mt-5 space-y-3">
          {(result.preview ?? []).map((p, i) => (
            <div key={i} className="rounded-xl border border-neutral-800 bg-neutral-900/50 p-4">
              <div className="text-[15px] font-semibold text-white">
                {i + 1}. {p.name}
              </div>
              <p className="mt-1.5 text-sm leading-relaxed text-neutral-400">{p.blurb}</p>
            </div>
          ))}
        </div>
        {(result.quick_wins?.length ?? 0) > 0 && (
          <div className="mt-5">
            <p className="text-xs font-semibold uppercase tracking-wider text-neutral-500">Free quick wins</p>
            <ul className="mt-2 space-y-1">
              {result.quick_wins!.map((q, i) => (
                <li key={i} className="text-sm leading-relaxed text-neutral-400">• {q}</li>
              ))}
            </ul>
          </div>
        )}
        <div className="mt-6 rounded-xl border border-neutral-800 bg-neutral-900/40 p-4">
          <p className="text-sm leading-relaxed text-neutral-300">
            The full assessment maps every process above plus the {Math.max(0, (result.total_processes ?? 3) - 3)} we
            didn&apos;t show, scored and sequenced into a build roadmap, walked through live. Fixed fee,
            scoped on a 20-minute call.
          </p>
          <a href={calUrl} target="_blank" rel="noreferrer" className={`${PRIMARY} mt-4`}>
            Book the walkthrough call →
          </a>
        </div>
      </div>
    );
  }

  if (stage === "error") {
    return (
      <div className="rounded-2xl border border-neutral-800 bg-neutral-950 p-6 text-sm text-neutral-400">
        Something broke on our side — your answers are saved. Email {" "}
        <a href="mailto:hello@contentdrip.ai" className="text-sky-400 hover:underline">hello@contentdrip.ai</a>{" "}
        or book a call and we&apos;ll run it live instead.
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-neutral-800 bg-neutral-950">
      <div className="max-h-[26rem] space-y-3 overflow-y-auto p-5">
        {messages.slice(1).map((m, i) => (
          <div key={i} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
            <div
              className={
                m.role === "user"
                  ? "max-w-[85%] rounded-2xl rounded-br-sm bg-sky-500/15 px-4 py-2.5 text-[14px] leading-relaxed text-sky-100"
                  : "max-w-[85%] rounded-2xl rounded-bl-sm border border-neutral-800 bg-neutral-900/60 px-4 py-2.5 text-[14px] leading-relaxed text-neutral-200"
              }
            >
              {m.content}
            </div>
          </div>
        ))}
        {(sending || stage === "compiling") && (
          <div className="flex justify-start">
            <div className="rounded-2xl border border-neutral-800 bg-neutral-900/60 px-4 py-2.5 text-[14px] text-neutral-500">
              {stage === "compiling" ? "compiling your process map…" : "…"}
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>
      {stage === "chat" && (
        <div className="flex gap-2 border-t border-neutral-800 p-3">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            placeholder="Type your answer…"
            className={INPUT}
            disabled={sending}
          />
          <button onClick={send} disabled={sending || !input.trim()} className={PRIMARY}>
            Send
          </button>
        </div>
      )}
    </div>
  );
}
