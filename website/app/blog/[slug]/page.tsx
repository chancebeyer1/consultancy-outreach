import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import ReactMarkdown from "react-markdown";

import { formatDate, getPost, listPosts } from "@/lib/blog";
import { SITE } from "@/lib/site";

export const revalidate = 900;

// Pre-render the posts we know about; ISR fills in new ones within the revalidate window.
export async function generateStaticParams() {
  const posts = await listPosts();
  return posts.map((p) => ({ slug: p.slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const post = await getPost(slug);
  if (!post) return { title: "Post not found" };
  const url = `${SITE.url}/blog/${post.slug}`;
  return {
    title: post.title,
    description: post.meta_description ?? undefined,
    alternates: { canonical: `/blog/${post.slug}` },
    openGraph: {
      title: post.title,
      description: post.meta_description ?? undefined,
      url,
      type: "article",
      publishedTime: post.published_at ?? undefined,
      siteName: SITE.name,
    },
    twitter: { card: "summary_large_image", title: post.title, description: post.meta_description ?? undefined },
  };
}

export default async function BlogPostPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const post = await getPost(slug);
  if (!post) notFound();

  const url = `${SITE.url}/blog/${post.slug}`;

  return (
    <article className="mx-auto max-w-3xl px-5 pb-24 pt-20 sm:px-8 sm:pt-28">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify({
            "@context": "https://schema.org",
            "@type": "BlogPosting",
            headline: post.title,
            description: post.meta_description,
            datePublished: post.published_at,
            dateModified: post.published_at,
            author: { "@type": "Organization", name: SITE.name, url: SITE.url },
            publisher: { "@type": "Organization", name: SITE.name, url: SITE.url },
            mainEntityOfPage: { "@type": "WebPage", "@id": url },
          }),
        }}
      />

      <Link href="/blog" className="text-sm text-neutral-500 transition-colors hover:text-sky-400">
        ← All posts
      </Link>

      <h1 className="mt-5 text-3xl font-semibold leading-[1.12] tracking-tight text-white sm:text-4xl">
        {post.title}
      </h1>
      <div className="mt-3 flex flex-wrap items-center gap-x-3 text-xs text-neutral-600">
        <time dateTime={post.published_at ?? undefined}>{formatDate(post.published_at)}</time>
        <span>Agentry</span>
        {post.tags?.slice(0, 4).map((t) => (
          <span key={t} className="text-neutral-500">
            #{t.replace(/\s+/g, "")}
          </span>
        ))}
      </div>

      {/* Featured image — the same auto-generated social card that unfurls on LinkedIn/X shares,
          shown here so each post has a header visual. Served by ./opengraph-image.tsx. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={`/blog/${post.slug}/opengraph-image`}
        alt={post.title}
        width={1200}
        height={630}
        className="mt-7 aspect-[1200/630] w-full rounded-2xl border border-neutral-800/80"
      />

      <div className="prose prose-invert mt-8 max-w-none prose-headings:font-semibold prose-headings:tracking-tight prose-a:text-sky-400 prose-a:no-underline hover:prose-a:underline prose-strong:text-white">
        <ReactMarkdown>{post.body_md}</ReactMarkdown>
      </div>

      {/* Conversion footer — every post funnels to a build conversation + the free tools. */}
      <div className="mt-12 rounded-2xl border border-sky-900/50 bg-sky-950/20 p-6 sm:p-8">
        <h2 className="text-lg font-semibold text-white">Want an agent like this built for your business?</h2>
        <p className="mt-2 text-[15px] leading-relaxed text-neutral-300">
          Agentry ships production AI agents in weeks. See where they&apos;d help you first with the
          free{" "}
          <Link href="/audit" className="text-sky-400 hover:underline">
            AI Opportunity Audit
          </Link>{" "}
          or{" "}
          <Link href="/tools" className="text-sky-400 hover:underline">
            the other tools
          </Link>
          , then book a call to scope it.
        </p>
        <a
          href={SITE.calUrl}
          target="_blank"
          rel="noreferrer"
          className="mt-5 inline-flex items-center justify-center rounded-full bg-sky-400 px-5 py-2.5 text-sm font-medium text-neutral-950 transition-colors hover:bg-sky-300"
        >
          Book a call →
        </a>
      </div>
    </article>
  );
}
