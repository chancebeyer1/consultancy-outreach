import { PageHeader } from "@/components/PageHeader";
import { dataSource, serverAdminClient } from "@/lib/supabase";

import { CommentsClient, type CommentItem } from "./CommentsClient";

export const dynamic = "force-dynamic";

export default async function CommentsPage() {
  let items: CommentItem[] = [];
  if (dataSource === "supabase") {
    const admin = serverAdminClient();
    const { data } = await admin
      .from("comment_queue")
      .select(
        "id, social_id, post_url, author_name, author_headline, post_excerpt, reactions, comments, keyword, body, status, error, approved_at, posted_at, created_at",
      )
      .neq("status", "rejected")
      .order("created_at", { ascending: false })
      .limit(80);
    items = (data ?? []) as CommentItem[];
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-6 sm:px-6">
      <PageHeader
        title="Comments"
        description="Thoughtful comments on big in-niche posts are the fastest way to grow a small account. Approve the ones you like — they post automatically, spaced across the day so it looks natural."
      />
      <CommentsClient items={items} />
    </div>
  );
}
