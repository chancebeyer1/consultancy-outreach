import { Analytics } from "@vercel/analytics/next";
import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { Suspense } from "react";

import { Nav } from "../components/Nav";
import { TopLoader } from "../components/TopLoader";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-sans", display: "swap" });

export const metadata: Metadata = {
  title: "Outreach dashboard",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="min-h-screen antialiased">
        <Suspense fallback={null}>
          <TopLoader />
        </Suspense>
        <Nav />
        <main>{children}</main>
        <Analytics />
      </body>
    </html>
  );
}
