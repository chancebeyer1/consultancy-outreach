"use client";

import { useEffect, useRef } from "react";

// A genuinely-3D rotating node network (agents + orchestration), drawn on a 2D canvas with
// real perspective projection. No WebGL/Three.js dependency, so it stays tiny and fast.
// Respects prefers-reduced-motion (renders a single static frame).
export function HeroCanvas() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ctx0 = el.getContext("2d");
    if (!ctx0) return;
    const canvas: HTMLCanvasElement = el;
    const ctx: CanvasRenderingContext2D = ctx0;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // Nodes scattered on a sphere; edges connect the near ones.
    const N = 84;
    const nodes = Array.from({ length: N }, () => {
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      return { x: Math.sin(phi) * Math.cos(theta), y: Math.sin(phi) * Math.sin(theta), z: Math.cos(phi) };
    });
    const edges: Array<[number, number]> = [];
    for (let i = 0; i < N; i++) {
      for (let j = i + 1; j < N; j++) {
        const dx = nodes[i].x - nodes[j].x;
        const dy = nodes[i].y - nodes[j].y;
        const dz = nodes[i].z - nodes[j].z;
        if (dx * dx + dy * dy + dz * dz < 0.34) edges.push([i, j]);
      }
    }

    let dpr = 1;
    function resize() {
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = canvas.clientWidth * dpr;
      canvas.height = canvas.clientHeight * dpr;
    }

    let raf = 0;
    let t = 0;
    const TILT = 0.42;
    const cosT = Math.cos(TILT);
    const sinT = Math.sin(TILT);

    function frame() {
      const W = canvas.width;
      const H = canvas.height;
      const cx = W / 2;
      const cy = H / 2;
      const scale = Math.min(W, H) * 0.46;
      ctx.clearRect(0, 0, W, H);

      const cy_ = Math.cos(t);
      const sy_ = Math.sin(t);
      const proj = nodes.map((n) => {
        // rotate around Y, then tilt around X, then project with perspective
        const x = n.x * cy_ - n.z * sy_;
        const z0 = n.x * sy_ + n.z * cy_;
        const y = n.y * cosT - z0 * sinT;
        const z = n.y * sinT + z0 * cosT;
        const persp = 2.6 / (2.6 - z);
        return { sx: cx + x * scale * persp, sy: cy + y * scale * persp, z, persp };
      });

      for (const [i, j] of edges) {
        const a = proj[i];
        const b = proj[j];
        const depth = (a.z + b.z) / 2; // -1 (back) .. 1 (front)
        const op = Math.max(0, (depth + 1) / 2) * 0.42;
        ctx.strokeStyle = `rgba(56,189,248,${op})`;
        ctx.lineWidth = dpr;
        ctx.beginPath();
        ctx.moveTo(a.sx, a.sy);
        ctx.lineTo(b.sx, b.sy);
        ctx.stroke();
      }
      for (const p of proj) {
        const r = Math.max(0.6, 2.3 * p.persp) * dpr;
        const op = 0.35 + ((p.z + 1) / 2) * 0.6;
        ctx.fillStyle = `rgba(125,211,252,${op})`;
        ctx.beginPath();
        ctx.arc(p.sx, p.sy, r, 0, Math.PI * 2);
        ctx.fill();
      }

      if (!reduce) {
        t += 0.0016;
        raf = requestAnimationFrame(frame);
      }
    }

    resize();
    frame();
    window.addEventListener("resize", () => {
      resize();
      if (reduce) frame();
    });
    return () => cancelAnimationFrame(raf);
  }, []);

  return <canvas ref={ref} className="h-full w-full" aria-hidden="true" />;
}
