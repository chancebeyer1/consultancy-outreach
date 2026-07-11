import { notFound } from "next/navigation";

import { getCurrentProfile } from "@/lib/auth";
import { getDealDetail } from "@/lib/queries";

import { DealDetailClient } from "./DealDetailClient";

export const dynamic = "force-dynamic";

export default async function DealPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const profile = await getCurrentProfile();
  const detail = await getDealDetail(id, profile);
  if (!detail) notFound();
  return (
    <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6">
      <DealDetailClient detail={detail} />
    </div>
  );
}
