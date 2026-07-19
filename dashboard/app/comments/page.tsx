import { PageHeader } from "@/components/PageHeader";
import { Pager } from "@/components/Pager";
import { requireAdmin } from "@/lib/auth";
import { dataSource, serverAdminClient } from "@/lib/supabase";

import { CommentsClient, type CommentItem } from "./CommentsClient";

export const dynamic = "force-dynamic";

// Newest-first pagination: the day's fresh drafts (needs-approval) land on page 1, and the posted
// history pages back — so the queue renders one page of cards instead of the whole backlog.
const PAGE_SIZE = 25;

export default async function CommentsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  await requireAdmin();
  const sp = await searchParams;
  const rawPage = Array.isArray(sp.page) ? sp.page[0] : sp.page;
  const page = Math.max(1, Number.parseInt(rawPage ?? "1", 10) || 1);

  let items: CommentItem[] = [];
  let total = 0;
  if (dataSource === "supabase") {
    const admin = serverAdminClient();
    const from = (page - 1) * PAGE_SIZE;
    const { data, count } = await admin
      .from("comment_queue")
      .select(
        "id, social_id, post_url, author_name, author_headline, post_excerpt, reactions, comments, keyword, body, status, error, approved_at, posted_at, created_at",
        { count: "exact" },
      )
      .neq("status", "rejected")
      .order("created_at", { ascending: false })
      .range(from, from + PAGE_SIZE - 1);
    items = (data ?? []) as CommentItem[];
    total = count ?? 0;
  }
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="mx-auto max-w-3xl px-4 py-6 sm:px-6">
      <PageHeader
        title="Comments"
        description="Thoughtful comments on big in-niche posts are the fastest way to grow a small account. Approve the ones you like — they post automatically, spaced across the day so it looks natural."
      />
      <CommentsClient items={items} />
      <Pager basePath="/comments" page={page} totalPages={totalPages} total={total} pageSize={PAGE_SIZE} unit="comments" />
    </div>
  );
}
