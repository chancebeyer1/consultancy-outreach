import type { Metadata } from "next";
import { Nav } from "../components/Nav";
import "./globals.css";

export const metadata: Metadata = {
  title: "Outreach dashboard",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <Nav />
        <main>{children}</main>
      </body>
    </html>
  );
}
