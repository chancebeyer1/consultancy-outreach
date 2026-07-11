// Blog data — fetched server-side from the Modal endpoints (public, read-only). ISR-cached so new
// daily posts appear within the revalidate window without a redeploy.
const LIST_URL =
  process.env.BLOG_LIST_URL || "https://chanceb323--consultancy-outreach-blog-list.modal.run";
const GET_URL =
  process.env.BLOG_GET_URL || "https://chanceb323--consultancy-outreach-blog-get.modal.run";

const REVALIDATE = 900; // 15 min — fresh enough for a daily blog, cached enough to be fast.

export type BlogSummary = {
  slug: string;
  title: string;
  meta_description: string | null;
  tags: string[];
  published_at: string | null;
};

export type BlogPost = BlogSummary & {
  body_md: string;
  source_title: string | null;
  source_url: string | null;
};

export async function listPosts(): Promise<BlogSummary[]> {
  try {
    const res = await fetch(LIST_URL, { next: { revalidate: REVALIDATE } });
    if (!res.ok) return [];
    const data = (await res.json()) as { posts?: BlogSummary[] };
    return data.posts ?? [];
  } catch {
    return [];
  }
}

export async function getPost(slug: string): Promise<BlogPost | null> {
  try {
    const res = await fetch(`${GET_URL}?slug=${encodeURIComponent(slug)}`, {
      next: { revalidate: REVALIDATE },
    });
    if (!res.ok) return null;
    const data = (await res.json()) as { post?: BlogPost | null };
    return data.post ?? null;
  } catch {
    return null;
  }
}

export function formatDate(iso: string | null): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" });
  } catch {
    return "";
  }
}
