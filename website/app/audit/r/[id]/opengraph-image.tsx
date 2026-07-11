import { ImageResponse } from "next/og";

export const runtime = "edge";
export const alt = "AI Opportunity Audit";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const RESULT_URL =
  process.env.RESULT_GET_URL || "https://chanceb323--consultancy-outreach-result-get.modal.run";

export default async function Image({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let company = "Your business";
  try {
    const res = await fetch(`${RESULT_URL}?kind=audit&id=${encodeURIComponent(id)}`);
    const data = await res.json();
    const c = data?.company || data?.result?.company;
    if (data?.ok && c) company = String(c).slice(0, 48);
  } catch {
    /* fall back to default */
  }

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          padding: "90px",
          backgroundColor: "#0a0a0b",
          fontFamily: "sans-serif",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", marginBottom: 28 }}>
          <div style={{ width: 20, height: 20, borderRadius: 9999, backgroundColor: "#38bdf8" }} />
          <div style={{ fontSize: 30, fontWeight: 600, color: "#ffffff", marginLeft: 16 }}>Agentry</div>
        </div>
        <div style={{ fontSize: 30, fontWeight: 600, color: "#38bdf8" }}>AI Opportunity Audit</div>
        <div style={{ fontSize: 66, fontWeight: 700, color: "#ffffff", marginTop: 12, lineHeight: 1.1 }}>
          {company}
        </div>
        <div style={{ fontSize: 30, color: "#a1a1aa", marginTop: 28, maxWidth: 900 }}>
          3 high-impact automations an AI agent could run, found in 30 seconds.
        </div>
      </div>
    ),
    { ...size },
  );
}
