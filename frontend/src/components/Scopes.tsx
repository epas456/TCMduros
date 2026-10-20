import { useEffect, useRef, useState } from "react";

/** Monitores de color (histograma RGB, forma de onda de luminancia y vectorscopio) a partir del visor. */
export default function Scopes({ source }: { source: () => HTMLCanvasElement | null }) {
  const histRef = useRef<HTMLCanvasElement>(null);
  const waveRef = useRef<HTMLCanvasElement>(null);
  const vecRef = useRef<HTMLCanvasElement>(null);
  const [mode, setMode] = useState<"all" | "hist" | "wave" | "vec">("all");

  useEffect(() => {
    const small = document.createElement("canvas");
    small.width = 192;
    small.height = 108;
    const sctx = small.getContext("2d", { willReadFrequently: true })!;
    const id = window.setInterval(() => {
      const src = source();
      if (!src || !src.width) return;
      sctx.drawImage(src, 0, 0, small.width, small.height);
      const { data } = sctx.getImageData(0, 0, small.width, small.height);
      drawHist(histRef.current, data);
      drawWave(waveRef.current, data, small.width, small.height);
      drawVec(vecRef.current, data);
    }, 200);
    return () => window.clearInterval(id);
  }, [source]);

  const show = (k: "hist" | "wave" | "vec") => mode === "all" || mode === k;
  return (
    <div className="scopes" onDoubleClick={(e) => e.stopPropagation()}>
      <div className="scopes-head">
        {(["all", "hist", "wave", "vec"] as const).map((m) => (
          <button key={m} className={`chip ${mode === m ? "active" : ""}`} onClick={() => setMode(m)}>
            {{ all: "Todos", hist: "Histograma", wave: "Forma de onda", vec: "Vectorscopio" }[m]}
          </button>
        ))}
      </div>
      <div className="scopes-body">
        <canvas ref={histRef} width={220} height={110} style={{ display: show("hist") ? "block" : "none" }} title="Histograma RGB" />
        <canvas ref={waveRef} width={220} height={110} style={{ display: show("wave") ? "block" : "none" }} title="Forma de onda (luminancia)" />
        <canvas ref={vecRef} width={110} height={110} style={{ display: show("vec") ? "block" : "none" }} title="Vectorscopio" />
      </div>
    </div>
  );
}

function drawHist(cv: HTMLCanvasElement | null, d: Uint8ClampedArray) {
  if (!cv || cv.style.display === "none") return;
  const ctx = cv.getContext("2d")!;
  const bins = [new Uint32Array(256), new Uint32Array(256), new Uint32Array(256)];
  for (let i = 0; i < d.length; i += 4) {
    bins[0][d[i]]++;
    bins[1][d[i + 1]]++;
    bins[2][d[i + 2]]++;
  }
  let max = 1;
  for (const b of bins) for (let i = 1; i < 255; i++) max = Math.max(max, b[i]);
  ctx.fillStyle = "#07080c";
  ctx.fillRect(0, 0, cv.width, cv.height);
  ctx.globalCompositeOperation = "lighter";
  const cols = ["rgba(255,60,60,0.7)", "rgba(60,255,90,0.7)", "rgba(70,120,255,0.7)"];
  bins.forEach((b, c) => {
    ctx.fillStyle = cols[c];
    for (let i = 0; i < 256; i++) {
      const h = Math.sqrt(b[i] / max) * (cv.height - 4);
      ctx.fillRect((i / 256) * cv.width, cv.height - h, cv.width / 256 + 0.5, h);
    }
  });
  ctx.globalCompositeOperation = "source-over";
}

function drawWave(cv: HTMLCanvasElement | null, d: Uint8ClampedArray, w: number, h: number) {
  if (!cv || cv.style.display === "none") return;
  const ctx = cv.getContext("2d")!;
  ctx.fillStyle = "#07080c";
  ctx.fillRect(0, 0, cv.width, cv.height);
  ctx.strokeStyle = "rgba(255,255,255,0.08)";
  for (const y of [0, 0.25, 0.5, 0.75, 1]) {
    ctx.beginPath();
    ctx.moveTo(0, y * (cv.height - 1) + 0.5);
    ctx.lineTo(cv.width, y * (cv.height - 1) + 0.5);
    ctx.stroke();
  }
  const img = ctx.getImageData(0, 0, cv.width, cv.height);
  const o = img.data;
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const i = (y * w + x) * 4;
      const luma = 0.2126 * d[i] + 0.7152 * d[i + 1] + 0.0722 * d[i + 2];
      const px = Math.floor((x / w) * cv.width);
      const py = Math.floor((1 - luma / 255) * (cv.height - 1));
      const j = (py * cv.width + px) * 4;
      o[j] = Math.min(255, o[j] + 40);
      o[j + 1] = Math.min(255, o[j + 1] + 70);
      o[j + 2] = Math.min(255, o[j + 2] + 40);
      o[j + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);
}

function drawVec(cv: HTMLCanvasElement | null, d: Uint8ClampedArray) {
  if (!cv || cv.style.display === "none") return;
  const ctx = cv.getContext("2d")!;
  const W = cv.width;
  ctx.fillStyle = "#07080c";
  ctx.fillRect(0, 0, W, W);
  ctx.strokeStyle = "rgba(255,255,255,0.12)";
  ctx.beginPath();
  ctx.arc(W / 2, W / 2, W / 2 - 2, 0, Math.PI * 2);
  ctx.moveTo(W / 2, 0);
  ctx.lineTo(W / 2, W);
  ctx.moveTo(0, W / 2);
  ctx.lineTo(W, W / 2);
  ctx.stroke();
  // línea de tono de piel (≈123°)
  ctx.strokeStyle = "rgba(255,170,90,0.35)";
  ctx.beginPath();
  ctx.moveTo(W / 2, W / 2);
  const a = (-123 * Math.PI) / 180;
  ctx.lineTo(W / 2 + Math.cos(a) * W / 2, W / 2 + Math.sin(a) * W / 2);
  ctx.stroke();
  const img = ctx.getImageData(0, 0, W, W);
  const o = img.data;
  for (let i = 0; i < d.length; i += 4) {
    const r = d[i], g = d[i + 1], b = d[i + 2];
    const cb = -0.1146 * r - 0.3854 * g + 0.5 * b;
    const cr = 0.5 * r - 0.4542 * g - 0.0458 * b;
    const x = Math.floor(W / 2 + (cb / 128) * (W / 2 - 2));
    const y = Math.floor(W / 2 - (cr / 128) * (W / 2 - 2));
    if (x < 0 || y < 0 || x >= W || y >= W) continue;
    const j = (y * W + x) * 4;
    o[j] = Math.min(255, o[j] + Math.max(30, r * 0.3));
    o[j + 1] = Math.min(255, o[j + 1] + Math.max(30, g * 0.3));
    o[j + 2] = Math.min(255, o[j + 2] + Math.max(30, b * 0.3));
    o[j + 3] = 255;
  }
  ctx.putImageData(img, 0, 0);
}
