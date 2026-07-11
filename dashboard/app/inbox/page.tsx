import { redirect } from "next/navigation";

// /inbox retired — /replies is now the single place for all inbound (LinkedIn + email, incl.
// OOO auto-replies shown greyed), with full threads + direct reply. Old links land on /replies.
export default function InboxPage() {
  redirect("/replies");
}
