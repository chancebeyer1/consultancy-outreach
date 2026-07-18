import type { MetadataRoute } from "next";

import { listPosts } from "@/lib/blog";
import { SITE } from "@/lib/site";
import { VERTICALS } from "@/lib/verticals";

export const revalidate = 900;

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const now = new Date();
  const entries: Array<{ path: string; priority: number; freq: "daily" | "weekly" | "monthly" }> = [
    { path: "", priority: 1.0, freq: "weekly" },
    { path: "/assessment", priority: 0.9, freq: "weekly" },
    { path: "/agent-ops", priority: 0.9, freq: "weekly" },
    { path: "/tools", priority: 0.9, freq: "weekly" },
    { path: "/audit", priority: 0.9, freq: "weekly" },
    { path: "/roi-calculator", priority: 0.9, freq: "weekly" },
    { path: "/roast", priority: 0.9, freq: "weekly" },
    { path: "/blog", priority: 0.8, freq: "daily" },
    { path: "/ai-agents-for", priority: 0.9, freq: "weekly" },
    // Every vertical landing page is a long-tail entry point ("AI agents for <industry>").
    ...VERTICALS.map((v) => ({
      path: `/ai-agents-for/${v.slug}`,
      priority: 0.8,
      freq: "weekly" as const,
    })),
    { path: "/writing", priority: 0.7, freq: "monthly" },
    { path: "/writing/ai-opportunity-audit", priority: 0.7, freq: "monthly" },
    { path: "/writing/autonomous-outreach-engine", priority: 0.7, freq: "monthly" },
  ];
  const staticEntries = entries.map((e) => ({
    url: `${SITE.url}${e.path}`,
    lastModified: now,
    changeFrequency: e.freq,
    priority: e.priority,
  }));

  // Every published blog post is its own indexable page.
  const posts = await listPosts();
  const postEntries = posts.map((p) => ({
    url: `${SITE.url}/blog/${p.slug}`,
    lastModified: p.published_at ? new Date(p.published_at) : now,
    changeFrequency: "monthly" as const,
    priority: 0.6,
  }));

  return [...staticEntries, ...postEntries];
}
