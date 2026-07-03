import { PageHeader } from "@/components/PageHeader";
import { requireAdmin } from "@/lib/auth";
import { dataSource, serverAdminClient } from "@/lib/supabase";

import { NewsletterClient, type Issue } from "./NewsletterClient";

export const dynamic = "force-dynamic";

export default async function NewsletterPage() {
  await requireAdmin();
  let issues: Issue[] = [];
  let subscribers = 0;
  if (dataSource === "supabase") {
    const admin = serverAdminClient();
    const [issuesRes, subsRes] = await Promise.all([
      admin
        .from("newsletter_issues")
        .select("id, subject, body, status, sent_at, recipients, error, created_at")
        .order("created_at", { ascending: false })
        .limit(10),
      admin.from("subscribers").select("id", { count: "exact", head: true }).is("unsubscribed_at", null),
    ]);
    issues = (issuesRes.data ?? []) as Issue[];
    subscribers = subsRes.count ?? 0;
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-6 sm:px-6">
      <PageHeader
        title="The Agent Brief"
        description="An agent drafts a weekly issue from the week's AI news. Review, edit, and send it to your subscribers — your owned audience."
      />
      <NewsletterClient issues={issues} subscribers={subscribers} />
    </div>
  );
}
