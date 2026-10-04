import { useEffect, useRef, useState } from "react";

type Tool = "brush" | "erase" | "lasso";

type Props = {
  imageJpegB64: string | null;
  /** Server-persisted seed alpha PNG (data URL or raw b64) — reloads after scrub. */
  initialMaskPngB64?: string | null;
  width: number;
  height: number;
  disabled?: boolean;
  onCommit: (pngB64: string) => void;
  onClear: () => void;
};

function drawMaskFromPng(
  ctx: CanvasRenderingContext2D,
  pngB64: string,
  w: number,
  h: number,
): Promise<void> {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => {
      // Convert grayscale/alpha PNG into amber overlay paint
      const off = document.createElement("canvas");
      off.width = w;
      off.height = h;
      const octx = off.getContext("2d");
      if (!octx) {
        resolve();
        return;
      }
      octx.drawImage(img, 0, 0, w, h);
      const data = octx.getImageData(0, 0, w, h);
      const out = ctx.createImageData(w, h);
      for (let i = 0; i < data.data.length; i += 4) {
        // Prefer alpha channel; else luminance
        const a = data.data[i + 3] < 250 ? data.data[i + 3] : data.data[i];
        if (a > 8) {
          out.data[i] = 212;
          out.data[i + 1] = 162;
          out.data[i + 2] = 76;
          out.data[i + 3] = Math.min(220, Math.round(a * 0.85));
        }
      }
      ctx.clearRect(0, 0, w, h);
      ctx.putImageData(out, 0, 0);
      resolve();
    };
    img.onerror = () => resolve();
    const src = pngB64.startsWith("data:") ? pngB64 : `data:image/png;base64,${pngB64}`;
    img.src = src;
  });
}

export function SeedPaint({
  imageJpegB64,
  initialMaskPngB64,
  width,
  height,
  disabled,
  onCommit,
  onClear,
}: Props) {
  const bgRef = useRef<HTMLCanvasElement>(null);
  const maskRef = useRef<HTMLCanvasElement>(null);
  const [tool, setTool] = useState<Tool>("brush");
  const [brush, setBrush] = useState(28);
  const drawing = useRef(false);
  const lasso = useRef<{ x: number; y: number }[]>([]);
  const [ready, setReady] = useState(false);
  const lastMaskKey = useRef<string | null>(null);
  const sizeKey = useRef("");

  const w = Math.max(160, width || 480);
  const h = Math.max(120, height || 360);

  // Background frame only — never wipe the seed overlay on scrub
  useEffect(() => {
    const bg = bgRef.current;
    const mask = maskRef.current;
    if (!bg || !mask) return;
    const resized = sizeKey.current !== `${w}x${h}`;
    if (resized) {
      // Preserve existing mask pixels across resize when possible
      const prev = document.createElement("canvas");
      prev.width = mask.width || w;
      prev.height = mask.height || h;
      const pctx = prev.getContext("2d");
      const mctx = mask.getContext("2d");
      if (pctx && mctx && mask.width && mask.height) {
        pctx.drawImage(mask, 0, 0);
      }
      bg.width = w;
      bg.height = h;
      mask.width = w;
      mask.height = h;
      if (pctx && mctx && prev.width && prev.height) {
        mctx.drawImage(prev, 0, 0, w, h);
      }
      sizeKey.current = `${w}x${h}`;
    } else {
      if (bg.width !== w) bg.width = w;
      if (bg.height !== h) bg.height = h;
      if (mask.width !== w) mask.width = w;
      if (mask.height !== h) mask.height = h;
    }
    const bctx = bg.getContext("2d");
    if (!bctx) return;
    if (!imageJpegB64) {
      bctx.fillStyle = "#122019";
      bctx.fillRect(0, 0, w, h);
      setReady(false);
      return;
    }
    const img = new Image();
    img.onload = () => {
      bctx.drawImage(img, 0, 0, w, h);
      setReady(true);
    };
    img.src = `data:image/jpeg;base64,${imageJpegB64}`;
  }, [imageJpegB64, w, h]);

  // Bind server seed once per mask payload (survives scrub / panel reopen)
  useEffect(() => {
    const mask = maskRef.current;
    if (!mask) return;
    const ctx = mask.getContext("2d");
    if (!ctx) return;
    const key = initialMaskPngB64 || "";
    if (!key) {
      if (lastMaskKey.current) {
        // Cleared on server
        ctx.clearRect(0, 0, mask.width, mask.height);
        lastMaskKey.current = null;
      }
      return;
    }
    if (lastMaskKey.current === key) return;
    lastMaskKey.current = key;
    void drawMaskFromPng(ctx, key, mask.width || w, mask.height || h);
  }, [initialMaskPngB64, w, h]);

  const pos = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const canvas = maskRef.current!;
    const rect = canvas.getBoundingClientRect();
    return {
      x: ((e.clientX - rect.left) / rect.width) * canvas.width,
      y: ((e.clientY - rect.top) / rect.height) * canvas.height,
    };
  };

  const paintAt = (x: number, y: number) => {
    const ctx = maskRef.current?.getContext("2d");
    if (!ctx) return;
    ctx.save();
    if (tool === "erase") {
      ctx.globalCompositeOperation = "destination-out";
      ctx.fillStyle = "rgba(0,0,0,1)";
    } else {
      ctx.globalCompositeOperation = "source-over";
      ctx.fillStyle = "rgba(212, 162, 76, 0.85)";
    }
    ctx.beginPath();
    ctx.arc(x, y, brush / 2, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  };

  const onPointerDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (disabled || !ready) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    drawing.current = true;
    const { x, y } = pos(e);
    if (tool === "lasso") {
      lasso.current = [{ x, y }];
    } else {
      paintAt(x, y);
    }
  };

  const onPointerMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!drawing.current || disabled) return;
    const { x, y } = pos(e);
    if (tool === "lasso") {
      lasso.current.push({ x, y });
      const ctx = maskRef.current?.getContext("2d");
      if (!ctx) return;
      ctx.save();
      ctx.strokeStyle = "rgba(212,162,76,0.95)";
      ctx.lineWidth = 2;
      ctx.beginPath();
      const pts = lasso.current;
      pts.forEach((p, i) => (i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y)));
      ctx.stroke();
      ctx.restore();
    } else {
      paintAt(x, y);
    }
  };

  const onPointerUp = () => {
    if (!drawing.current) return;
    drawing.current = false;
    if (tool === "lasso" && lasso.current.length > 2) {
      const ctx = maskRef.current?.getContext("2d");
      if (ctx) {
        ctx.save();
        ctx.globalCompositeOperation = "source-over";
        ctx.fillStyle = "rgba(212, 162, 76, 0.85)";
        ctx.beginPath();
        lasso.current.forEach((p, i) => (i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y)));
        ctx.closePath();
        ctx.fill();
        ctx.restore();
      }
      lasso.current = [];
    }
  };

  const commit = () => {
    const mask = maskRef.current;
    if (!mask) return;
    const ctx = mask.getContext("2d");
    if (!ctx) return;
    const imgData = ctx.getImageData(0, 0, mask.width, mask.height);
    const alpha = document.createElement("canvas");
    alpha.width = mask.width;
    alpha.height = mask.height;
    const actx = alpha.getContext("2d");
    if (!actx) return;
    const out = actx.createImageData(mask.width, mask.height);
    for (let i = 0; i < imgData.data.length; i += 4) {
      const a = imgData.data[i + 3];
      out.data[i] = a;
      out.data[i + 1] = a;
      out.data[i + 2] = a;
      out.data[i + 3] = 255;
    }
    actx.putImageData(out, 0, 0);
    const dataUrl = alpha.toDataURL("image/png");
    lastMaskKey.current = dataUrl;
    onCommit(dataUrl);
  };

  const localClear = () => {
    const mask = maskRef.current;
    const ctx = mask?.getContext("2d");
    if (mask && ctx) ctx.clearRect(0, 0, mask.width, mask.height);
    lastMaskKey.current = null;
    onClear();
  };

  return (
    <div className="seed-paint">
      <div className="seed-tools">
        <button
          type="button"
          className={`btn ${tool === "brush" ? "primary" : ""}`}
          disabled={disabled}
          title="Ecset: alany hozzáadása a kézi maszkhoz."
          onClick={() => setTool("brush")}
        >
          Ecset
        </button>
        <button
          type="button"
          className={`btn ${tool === "erase" ? "primary" : ""}`}
          disabled={disabled}
          title="Radír: téves maszkterület törlése."
          onClick={() => setTool("erase")}
        >
          Radír
        </button>
        <button
          type="button"
          className={`btn ${tool === "lasso" ? "primary" : ""}`}
          disabled={disabled}
          title="Lasszó: zárt terület kijelölése a maszkhoz."
          onClick={() => setTool("lasso")}
        >
          Lasszó
        </button>
        <label className="brush-size" title="Ecset / radír mérete.">
          Méret
          <input
            type="range"
            min={8}
            max={72}
            value={brush}
            disabled={disabled}
            onChange={(e) => setBrush(Number(e.target.value))}
          />
        </label>
      </div>
      <div className="seed-stage">
        <canvas ref={bgRef} className="seed-bg" />
        <canvas
          ref={maskRef}
          className="seed-mask"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerLeave={onPointerUp}
          title="Fesd a kézi maszkot a forrás képkockára."
        />
      </div>
      <div className="seed-actions">
        <button
          type="button"
          className="btn accent"
          disabled={disabled || !ready}
          onClick={commit}
          title="Kézi maszk mentése a szerverre (scrub után is megmarad)."
        >
          Maszk mentése
        </button>
        <button
          type="button"
          className="btn"
          disabled={disabled}
          onClick={localClear}
          title="Kézi maszk törlése."
        >
          Maszk törlése
        </button>
      </div>
      <p className="seed-hint">
        Forrás a maszk alatt. A kézi maszk scrub után is megmarad. Export → Max minőség /
        MatAnyone2.
      </p>
    </div>
  );
}
