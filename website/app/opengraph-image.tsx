import { ImageResponse } from "next/og";

// 1200×630 social card. CENTERED on purpose: LinkedIn's Featured section crops narrower than
// 1.91:1, so left-aligned text loses its edges ("Production…shipped" → "duction…pped"). Centering
// with wide margins keeps the brand + headline readable under a symmetric crop. LinkedIn caches
// hard — after deploy, re-scrape at linkedin.com/post-inspector to refresh the Featured thumbnail.
export const runtime = "edge";
export const alt = "Agentry — Production AI agents, shipped in weeks";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpengraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          textAlign: "center",
          backgroundColor: "#0a0a0b",
          fontFamily: "sans-serif",
          padding: "80px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", marginBottom: 40 }}>
          <div style={{ width: 22, height: 22, borderRadius: 9999, backgroundColor: "#38bdf8" }} />
          <div style={{ fontSize: 34, fontWeight: 700, color: "#ffffff", marginLeft: 16, letterSpacing: 2 }}>
            Agentry
          </div>
        </div>
        <div
          style={{
            fontSize: 64,
            fontWeight: 700,
            color: "#ffffff",
            lineHeight: 1.12,
            maxWidth: 760,
            textAlign: "center",
          }}
        >
          Production AI agents, shipped in weeks.
        </div>
        <div
          style={{
            fontSize: 28,
            color: "#a1a1aa",
            marginTop: 30,
            maxWidth: 680,
            lineHeight: 1.4,
            textAlign: "center",
          }}
        >
          An independent studio that builds &amp; ships autonomous AI agents end to end.
        </div>
      </div>
    ),
    { ...size },
  );
}
