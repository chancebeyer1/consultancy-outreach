import { ImageResponse } from "next/og";

// Per-post 1200×630 social card. This is the "viral" image that unfurls when a post link is shared
// on LinkedIn / X / Slack (and the auto-drafted LinkedIn promo appends the blog URL, so its preview
// picks this up automatically). File convention: it overrides the generic homepage card for every
// /blog/<slug> route with a headline-specific card — zero per-post work, no image API, no storage.
// LinkedIn caches hard; after a design change re-scrape at linkedin.com/post-inspector.
export const runtime = "edge";
export const alt = "Agentry blog post";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const GET_URL =
  process.env.BLOG_GET_URL || "https://chanceb323--consultancy-outreach-blog-get.modal.run";

// Scale the headline down as it gets longer so it always fits in ~3 lines without overflow.
function titleSize(len: number): number {
  if (len <= 30) return 74;
  if (len <= 45) return 64;
  if (len <= 60) return 54;
  return 46;
}

export default async function Image({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  let title = "AI agents, in plain English";
  let eyebrow = "AI AGENTS";
  try {
    const res = await fetch(`${GET_URL}?slug=${encodeURIComponent(slug)}`);
    const data = await res.json();
    const post = data?.post;
    if (post?.title) title = String(post.title).slice(0, 90);
    const tag = Array.isArray(post?.tags) ? post.tags[0] : null;
    if (tag) eyebrow = String(tag).toUpperCase().slice(0, 28);
  } catch {
    /* fall back to defaults */
  }

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: "78px 90px",
          backgroundColor: "#0a0a0b",
          backgroundImage:
            "radial-gradient(900px circle at 100% 0%, rgba(56,189,248,0.16), rgba(10,10,11,0) 55%)",
          fontFamily: "sans-serif",
        }}
      >
        {/* Brand row */}
        <div style={{ display: "flex", alignItems: "center" }}>
          <div style={{ width: 22, height: 22, borderRadius: 9999, backgroundColor: "#38bdf8" }} />
          <div style={{ fontSize: 32, fontWeight: 700, color: "#ffffff", marginLeft: 16, letterSpacing: 1 }}>
            Agentry
          </div>
          <div style={{ fontSize: 26, color: "#52525b", marginLeft: 16 }}>· Blog</div>
        </div>

        {/* Headline block */}
        <div style={{ display: "flex", flexDirection: "column" }}>
          <div style={{ fontSize: 26, fontWeight: 600, color: "#38bdf8", letterSpacing: 3, marginBottom: 22 }}>
            {eyebrow}
          </div>
          <div
            style={{
              fontSize: titleSize(title.length),
              fontWeight: 700,
              color: "#ffffff",
              lineHeight: 1.12,
              maxWidth: 1000,
            }}
          >
            {title}
          </div>
        </div>

        {/* Footer: accent rule + domain for brand recall on shares */}
        <div style={{ display: "flex", alignItems: "center" }}>
          <div style={{ width: 56, height: 4, borderRadius: 9999, backgroundColor: "#38bdf8" }} />
          <div style={{ fontSize: 24, color: "#a1a1aa", marginLeft: 18 }}>
            agentry.contentdrip.ai
          </div>
        </div>
      </div>
    ),
    { ...size },
  );
}
