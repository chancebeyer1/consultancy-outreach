import { PageHeader } from "@/components/PageHeader";
import { requireAdmin } from "@/lib/auth";
import { dataSource, serverAdminClient } from "@/lib/supabase";

import { ContentClient, type ContentPost } from "./ContentClient";

export const dynamic = "force-dynamic";

export type BlogStats = { count: number; last: string | null; slug: string | null };

// "Recent" (already-actioned) posts are paginated so the page stays light no matter how many have
// accumulated. Drafts are never paginated — they're the actionable queue and shown in full.
const PAGE_SIZE = 20;
const POST_COLS =
  "id, source_title, source_url, discussion_url, body, format, image_idea, card_image, media_images, status, external_id, error, created_at, posted_at";

export default async function ContentPage({
  searchParams,
}: {
  searchParams: Promise<{ page?: string }>;
}) {
  await requireAdmin();
  const page = Math.max(1, Number.parseInt((await searchParams).page ?? "1", 10) || 1);

  let drafts: ContentPost[] = [];
  let recent: ContentPost[] = [];
  let recentTotal = 0;
  let autoBlog = false;
  let blogStats: BlogStats = { count: 0, last: null, slug: null };

  if (dataSource === "supabase") {
    const admin = serverAdminClient();
    const from = (page - 1) * PAGE_SIZE;
    const to = from + PAGE_SIZE - 1;

    // Fire every read in parallel — previously these ran sequentially, so each navigation to this
    // page waited on four round-trips back to back.
    const [draftsRes, recentRes, settingRes, blogCountRes, latestRes] = await Promise.all([
      admin
        .from("content_posts")
        .select(POST_COLS)
        .eq("status", "draft")
        .order("created_at", { ascending: false })
        .limit(50),
      admin
        .from("content_posts")
        .select(POST_COLS, { count: "exact" })
        .neq("status", "rejected")
        .neq("status", "draft")
        .order("created_at", { ascending: false })
        .range(from, to),
      admin.from("app_settings").select("value").eq("key", "auto_blog").maybeSingle(),
      admin.from("blog_posts").select("id", { count: "exact", head: true }).eq("status", "published"),
      admin
        .from("blog_posts")
        .select("slug, published_at")
        .eq("status", "published")
        .order("published_at", { ascending: false })
        .limit(1),
    ]);

    drafts = (draftsRes.data ?? []) as ContentPost[];
    recent = (recentRes.data ?? []) as ContentPost[];
    recentTotal = recentRes.count ?? 0;
    autoBlog = settingRes.data?.value === true;
    blogStats = {
      count: blogCountRes.count ?? 0,
      last: latestRes.data?.[0]?.published_at ?? null,
      slug: latestRes.data?.[0]?.slug ?? null,
    };
  }

  const totalPages = Math.max(1, Math.ceil(recentTotal / PAGE_SIZE));

  return (
    <div className="mx-auto max-w-3xl px-4 py-6 sm:px-6">
      <PageHeader
        title="Content"
        description="LinkedIn posts drafted from recent AI news, in your voice. Review and edit, then approve — approved posts publish to your LinkedIn automatically within the hour."
      />
      <ContentClient
        drafts={drafts}
        recent={recent}
        page={page}
        totalPages={totalPages}
        recentTotal={recentTotal}
        autoBlog={autoBlog}
        blogStats={blogStats}
      />
    </div>
  );
}
