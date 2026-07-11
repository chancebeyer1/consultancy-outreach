import { ImageResponse } from "next/og";

export const runtime = "edge";
export const alt = "Cold Outreach Roast";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const RESULT_URL =
  process.env.RESULT_GET_URL || "https://chanceb323--consultancy-outreach-result-get.modal.run";

export default async function Image({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let grade = "?";
  let verdict = "An AI agent graded this cold outreach.";
  try {
    const res = await fetch(`${RESULT_URL}?kind=roast&id=${encodeURIComponent(id)}`);
    const data = await res.json();
    if (data?.ok && data.result) {
      if (data.result.grade) grade = String(data.result.grade).slice(0, 4);
      if (data.result.verdict) verdict = String(data.result.verdict).slice(0, 120);
    }
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
        <div style={{ fontSize: 30, fontWeight: 600, color: "#38bdf8" }}>Cold Outreach Roast</div>
        <div style={{ display: "flex", alignItems: "center", marginTop: 18 }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              width: 150,
              height: 150,
              borderRadius: 28,
              border: "2px solid #1f2937",
              color: "#38bdf8",
              fontSize: 90,
              fontWeight: 700,
            }}
          >
            {grade}
          </div>
          <div style={{ fontSize: 40, fontWeight: 600, color: "#ffffff", marginLeft: 36, maxWidth: 720, lineHeight: 1.2 }}>
            {verdict}
          </div>
        </div>
      </div>
    ),
    { ...size },
  );
}
