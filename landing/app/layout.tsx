import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  // TODO: replace with your name + tagline
  title: "Your Name — AI agent contractor",
  description:
    "Independent contractor shipping production AI agents. Recent contract delivering a production agent; open to new engagements.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen">{children}</body>
    </html>
  );
}
