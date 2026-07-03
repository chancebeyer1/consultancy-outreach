import { PageHeader } from "@/components/PageHeader";
import { requireAdmin } from "@/lib/auth";
import { dataSource, serverAdminClient } from "@/lib/supabase";

import { ContentClient, type ContentPost } from "./ContentClient";

export const dynamic = "force-dynamic";

export type BlogStats = { count: number; last: string | null; slug: string | null };

export default async function ContentPage() {
  await requireAdmin();
  let posts: ContentPost[] = [];
  let autoBlog = false;
  let blogStats: BlogStats = { count: 0, last: null, slug: null };
  if (dataSource === "supabase") {
    const admin = serverAdminClient();
    const { data } = await admin
      .from("content_posts")
      .select(
        "id, source_title, source_url, discussion_url, body, format, image_idea, card_image, status, external_id, error, created_at, posted_at",
      )
      .neq("status", "rejected")
      .order("created_at", { ascending: false })
      .limit(40);
    posts = (data ?? []) as ContentPost[];

    const { data: setting } = await admin
      .from("app_settings")
      .select("value")
      .eq("key", "auto_blog")
      .maybeSingle();
    autoBlog = setting?.value === true;

    const { count } = await admin
      .from("blog_posts")
      .select("id", { count: "exact", head: true })
      .eq("status", "published");
    const { data: latest } = await admin
      .from("blog_posts")
      .select("slug, published_at")
      .eq("status", "published")
      .order("published_at", { ascending: false })
      .limit(1);
    blogStats = { count: count ?? 0, last: latest?.[0]?.published_at ?? null, slug: latest?.[0]?.slug ?? null };
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-6 sm:px-6">
      <PageHeader
        title="Content"
        description="LinkedIn posts drafted from recent AI news, in your voice. Review and edit, then approve — approved posts publish to your LinkedIn automatically within the hour."
      />
      <ContentClient posts={posts} autoBlog={autoBlog} blogStats={blogStats} />
    </div>
  );
}
