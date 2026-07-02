import Link from "next/link";

import { formatDate, listPosts } from "@/lib/blog";

export const revalidate = 900;

export const metadata = {
  title: "AI Agents Blog",
  description:
    "Practical takes on AI agents, automation, and building production AI — grounded in the latest news, from the Agentry studio. Updated daily.",
  alternates: { canonical: "/blog" },
};

export default async function BlogIndex() {
  const posts = await listPosts();

  return (
    <section className="mx-auto max-w-3xl px-5 pb-24 pt-20 sm:px-8 sm:pt-28">
      <p className="mb-6 inline-flex items-center gap-2 rounded-full border border-neutral-800 bg-neutral-900/50 px-3 py-1 text-xs text-neutral-400">
        <span className="h-1.5 w-1.5 rounded-full bg-sky-400" /> New posts, most days
      </p>
      <h1 className="text-4xl font-semibold leading-[1.08] tracking-tight text-white sm:text-5xl">
        The Agentry <span className="text-sky-400">blog</span>
      </h1>
      <p className="mt-6 max-w-2xl text-lg leading-relaxed text-neutral-400">
        Practical, no-hype takes on AI agents and automation — what the latest news means for
        actually building this stuff, from a studio that ships it.
      </p>

      {posts.length === 0 ? (
        <p className="mt-12 rounded-xl border border-neutral-800 bg-neutral-950 px-4 py-8 text-center text-sm italic text-neutral-500">
          First posts are on the way.
        </p>
      ) : (
        <div className="mt-12 space-y-5">
          {posts.map((p) => (
            <article key={p.slug} className="border-b border-neutral-900 pb-5 last:border-0">
              <Link href={`/blog/${p.slug}`} className="group block">
                <h2 className="text-xl font-semibold text-white transition-colors group-hover:text-sky-400">
                  {p.title}
                </h2>
                {p.meta_description && (
                  <p className="mt-1.5 text-[15px] leading-relaxed text-neutral-400">{p.meta_description}</p>
                )}
                <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-neutral-600">
                  <time dateTime={p.published_at ?? undefined}>{formatDate(p.published_at)}</time>
                  {p.tags?.slice(0, 3).map((t) => (
                    <span key={t} className="text-neutral-500">
                      #{t.replace(/\s+/g, "")}
                    </span>
                  ))}
                </div>
              </Link>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
