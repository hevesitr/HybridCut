import { useEffect, useRef, useState, type ReactNode } from "react";

type Tool = "brush" | "erase" | "lasso" | "wand";

type Props = {
  imageJpegB64: string | null;
  /** Server-persisted seed alpha PNG (data URL or raw b64) — reloads after scrub. */
  initialMaskPngB64?: string | null;
  width: number;
  height: number;
  disabled?: boolean;
  /**
   * panel = duplicate stage below;
   * docked = tools/actions in chrome outside the frame; canvas overlays `frame`.
   */
  variant?: "panel" | "docked";
  /** Preview frame (img / wipe) — only used with variant=docked. */
  frame?: ReactNode;
  /** Commit seed after each stroke (live cutout refresh). Debounced by parent. */
  autoCommitOnStrokeEnd?: boolean;
  onCommit: (pngB64: string) => void;
  onClear: () => void;
};

const AMBER = "rgba(212, 162, 76, 0.85)";

function drawMaskFromPng(
  ctx: CanvasRenderingContext2D,
  pngB64: string,
  w: number,
  h: number,
): Promise<void> {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => {
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
        // Seed PNG is grayscale alpha (R=G=B=a). Prefer luminance of paint PNG.
        const lum = data.data[i];
        const aCh = data.data[i + 3];
        const a = aCh < 250 ? Math.min(lum, aCh) : lum;
        if (a > 12) {
          out.data[i] = 212;
          out.data[i + 1] = 162;
          out.data[i + 2] = 76;
          out.data[i + 3] = Math.min(200, Math.round(a * 0.75));
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

function colorDist(r0: number, g0: number, b0: number, r1: number, g1: number, b1: number) {
  const dr = r0 - r1;
  const dg = g0 - g1;
  const db = b0 - b1;
  return Math.sqrt(dr * dr + dg * dg + db * db);
}

/** Flood-fill connected region on mask from reference RGB (Varázsceruza). */
function floodFillMask(
  maskCtx: CanvasRenderingContext2D,
  ref: ImageData,
  sx: number,
  sy: number,
  tolerance: number,
  erase: boolean,
) {
  const w = ref.width;
  const h = ref.height;
  const x0 = Math.max(0, Math.min(w - 1, Math.round(sx)));
  const y0 = Math.max(0, Math.min(h - 1, Math.round(sy)));
  const mask = maskCtx.getImageData(0, 0, w, h);
  const md = mask.data;
  const rd = ref.data;
  const i0 = (y0 * w + x0) * 4;
  const tr = rd[i0];
  const tg = rd[i0 + 1];
  const tb = rd[i0 + 2];
  const visited = new Uint8Array(w * h);
  const stack: number[] = [x0, y0];
  let painted = 0;
  const maxPaint = Math.floor(w * h * 0.45); // never flood >45% of frame (face-blob guard)

  while (stack.length) {
    const y = stack.pop()!;
    const x = stack.pop()!;
    if (x < 0 || y < 0 || x >= w || y >= h) continue;
    const idx = y * w + x;
    if (visited[idx]) continue;
    visited[idx] = 1;
    const pi = idx * 4;
    if (colorDist(rd[pi], rd[pi + 1], rd[pi + 2], tr, tg, tb) > tolerance) continue;
    if (erase) {
      md[pi] = 0;
      md[pi + 1] = 0;
      md[pi + 2] = 0;
      md[pi + 3] = 0;
    } else {
      md[pi] = 212;
      md[pi + 1] = 162;
      md[pi + 2] = 76;
      md[pi + 3] = 200;
    }
    painted += 1;
    if (painted > maxPaint) break;
    stack.push(x + 1, y, x - 1, y, x, y + 1, x, y - 1);
  }
  maskCtx.putImageData(mask, 0, 0);
  return painted;
}

export function SeedPaint({
  imageJpegB64,
  initialMaskPngB64,
  width,
  height,
  disabled,
  variant = "panel",
  frame,
  autoCommitOnStrokeEnd = false,
  onCommit,
  onClear,
}: Props) {
  const bgRef = useRef<HTMLCanvasElement>(null);
  const maskRef = useRef<HTMLCanvasElement>(null);
  const frameWrapRef = useRef<HTMLDivElement>(null);
  const imgProbeRef = useRef<HTMLImageElement | null>(null);
  const refRgb = useRef<ImageData | null>(null);
  const [tool, setTool] = useState<Tool>("brush");
  const [brush, setBrush] = useState(28);
  const [wandTol, setWandTol] = useState(28);
  const drawing = useRef(false);
  const dirty = useRef(false);
  const lasso = useRef<{ x: number; y: number }[]>([]);
  const pointerId = useRef<number | null>(null);
  const [ready, setReady] = useState(false);
  const lastMaskKey = useRef<string | null>(null);
  const sizeKey = useRef("");
  const docked = variant === "docked";

  const w = Math.max(160, width || 480);
  const h = Math.max(120, height || 360);

  // Keep mask canvas CSS box aligned to the displayed <img> (letterbox-safe).
  useEffect(() => {
    if (!docked) return;
    const wrap = frameWrapRef.current;
    if (!wrap) return;

    const sync = () => {
      const mask = maskRef.current;
      if (!mask) return;
      const img =
        wrap.querySelector("img.preview-cutout, img.wipe-base, img.wipe-fg") ||
        wrap.querySelector("img");
      if (!(img instanceof HTMLImageElement)) {
        mask.style.inset = "0";
        mask.style.width = "100%";
        mask.style.height = "100%";
        mask.style.left = "0";
        mask.style.top = "0";
        mask.style.transform = "none";
        return;
      }
      imgProbeRef.current = img;
      const wr = wrap.getBoundingClientRect();
      const ir = img.getBoundingClientRect();
      if (wr.width < 1 || wr.height < 1) return;
      mask.style.position = "absolute";
      mask.style.left = `${ir.left - wr.left}px`;
      mask.style.top = `${ir.top - wr.top}px`;
      mask.style.width = `${ir.width}px`;
      mask.style.height = `${ir.height}px`;
      mask.style.right = "auto";
      mask.style.bottom = "auto";
      mask.style.transform = "none";
    };

    sync();
    const ro = new ResizeObserver(() => sync());
    ro.observe(wrap);
    const img = wrap.querySelector("img");
    if (img) ro.observe(img);
    window.addEventListener("resize", sync);
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", sync);
    };
  }, [docked, imageJpegB64, width, height, frame]);

  // Background / reference RGB for wand + panel mode
  useEffect(() => {
    const bg = bgRef.current;
    const mask = maskRef.current;
    if (!mask) return;
    const resized = sizeKey.current !== `${w}x${h}`;
    if (resized) {
      const prev = document.createElement("canvas");
      prev.width = mask.width || w;
      prev.height = mask.height || h;
      const pctx = prev.getContext("2d");
      const mctx = mask.getContext("2d");
      if (pctx && mctx && mask.width && mask.height) {
        pctx.drawImage(mask, 0, 0);
      }
      if (bg) {
        bg.width = w;
        bg.height = h;
      }
      mask.width = w;
      mask.height = h;
      if (pctx && mctx && prev.width && prev.height) {
        mctx.drawImage(prev, 0, 0, w, h);
      }
      sizeKey.current = `${w}x${h}`;
      refRgb.current = null;
    } else {
      if (bg) {
        if (bg.width !== w) bg.width = w;
        if (bg.height !== h) bg.height = h;
      }
      if (mask.width !== w) mask.width = w;
      if (mask.height !== h) mask.height = h;
    }

    const applyRef = (img: HTMLImageElement) => {
      const off = document.createElement("canvas");
      off.width = w;
      off.height = h;
      const octx = off.getContext("2d");
      if (!octx) return;
      octx.drawImage(img, 0, 0, w, h);
      refRgb.current = octx.getImageData(0, 0, w, h);
      if (bg) {
        const bctx = bg.getContext("2d");
        bctx?.drawImage(img, 0, 0, w, h);
      }
      setReady(true);
    };

    if (!imageJpegB64) {
      if (bg) {
        const bctx = bg.getContext("2d");
        if (bctx) {
          bctx.fillStyle = "#122019";
          bctx.fillRect(0, 0, w, h);
        }
      }
      refRgb.current = null;
      setReady(docked); // docked can paint once frame exists
      return;
    }
    const img = new Image();
    img.onload = () => applyRef(img);
    img.src = `data:image/jpeg;base64,${imageJpegB64}`;
  }, [imageJpegB64, w, h, docked]);

  // Bind server seed once per mask payload (survives scrub / panel reopen)
  useEffect(() => {
    const mask = maskRef.current;
    if (!mask) return;
    const ctx = mask.getContext("2d");
    if (!ctx) return;
    const key = initialMaskPngB64 || "";
    if (!key) {
      if (lastMaskKey.current) {
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
      x: ((e.clientX - rect.left) / Math.max(1, rect.width)) * canvas.width,
      y: ((e.clientY - rect.top) / Math.max(1, rect.height)) * canvas.height,
    };
  };

  const releasePointer = (target: HTMLCanvasElement) => {
    const id = pointerId.current;
    if (id != null) {
      try {
        if (target.hasPointerCapture?.(id)) target.releasePointerCapture(id);
      } catch {
        /* ignore */
      }
      pointerId.current = null;
    }
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
      ctx.fillStyle = AMBER;
    }
    ctx.beginPath();
    ctx.arc(x, y, brush / 2, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
    dirty.current = true;
  };

  const endStroke = (target: HTMLCanvasElement) => {
    if (!drawing.current) {
      releasePointer(target);
      return;
    }
    drawing.current = false;
    releasePointer(target);

    if (tool === "lasso" && lasso.current.length > 2) {
      const ctx = maskRef.current?.getContext("2d");
      if (ctx) {
        // Clear the temporary stroke polyline by redrawing fill only on closed path.
        // Snapshot before stroke was drawn is expensive; instead fill closed path over strokes.
        ctx.save();
        ctx.globalCompositeOperation = "source-over";
        ctx.fillStyle = AMBER;
        ctx.beginPath();
        lasso.current.forEach((p, i) => (i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y)));
        ctx.closePath();
        ctx.fill();
        ctx.restore();
        dirty.current = true;
      }
      lasso.current = [];
    }

    if (autoCommitOnStrokeEnd && dirty.current && !disabled && ready) {
      commit();
    }
  };

  const onPointerDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (disabled || !ready) return;
    e.preventDefault();
    try {
      e.currentTarget.setPointerCapture(e.pointerId);
      pointerId.current = e.pointerId;
    } catch {
      pointerId.current = e.pointerId;
    }
    const { x, y } = pos(e);

    if (tool === "wand") {
      const ref = refRgb.current;
      const ctx = maskRef.current?.getContext("2d");
      if (ref && ctx) {
        floodFillMask(ctx, ref, x, y, wandTol, false);
        dirty.current = true;
        drawing.current = false;
        releasePointer(e.currentTarget);
        if (autoCommitOnStrokeEnd) commit();
      }
      return;
    }

    drawing.current = true;
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
      if (!ctx || lasso.current.length < 2) return;
      const pts = lasso.current;
      const a = pts[pts.length - 2];
      const b = pts[pts.length - 1];
      ctx.save();
      ctx.strokeStyle = "rgba(212,162,76,0.95)";
      ctx.lineWidth = 2;
      ctx.lineCap = "round";
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
      ctx.restore();
      dirty.current = true;
    } else if (tool === "brush" || tool === "erase") {
      paintAt(x, y);
    }
  };

  const onPointerUp = (e: React.PointerEvent<HTMLCanvasElement>) => {
    endStroke(e.currentTarget);
  };

  const onPointerCancel = (e: React.PointerEvent<HTMLCanvasElement>) => {
    drawing.current = false;
    lasso.current = [];
    releasePointer(e.currentTarget);
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
    dirty.current = false;
    onCommit(dataUrl);
  };

  const localClear = () => {
    const mask = maskRef.current;
    const ctx = mask?.getContext("2d");
    if (mask && ctx) ctx.clearRect(0, 0, mask.width, mask.height);
    lastMaskKey.current = null;
    dirty.current = false;
    onClear();
  };

  const tools = (
    <div className="seed-tools" role="toolbar" aria-label="Kézi maszk eszközök">
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
        title="Lasszó: zárt terület kijelölése a maszkhoz (enged el a bezáráshoz)."
        onClick={() => setTool("lasso")}
      >
        Lasszó
      </button>
      <button
        type="button"
        className={`btn ${tool === "wand" ? "primary" : ""}`}
        disabled={disabled}
        title="Varázsceruza: kattints a hasonló színű terület kijelöléséhez (flood-fill)."
        onClick={() => setTool("wand")}
      >
        Varázsceruza
      </button>
      <label className="brush-size" title="Ecset / radír mérete.">
        Méret
        <input
          type="range"
          min={8}
          max={72}
          value={brush}
          disabled={disabled || tool === "wand"}
          onChange={(e) => setBrush(Number(e.target.value))}
        />
      </label>
      {tool === "wand" ? (
        <label className="brush-size" title="Varázsceruza tűrése (színkülönbség).">
          Tűrés
          <input
            type="range"
            min={8}
            max={64}
            value={wandTol}
            disabled={disabled}
            onChange={(e) => setWandTol(Number(e.target.value))}
          />
        </label>
      ) : null}
    </div>
  );

  const actions = (
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
  );

  const maskCanvas = (
    <canvas
      ref={maskRef}
      className="seed-mask"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerCancel}
      title={
        tool === "wand"
          ? "Varázsceruza — kattints a kijelölendő területre"
          : "Fesd a kézi maszkot a forrás képkockára."
      }
    />
  );

  if (docked) {
    return (
      <div className="seed-paint seed-paint--docked">
        {tools}
        <div className="seed-frame" ref={frameWrapRef}>
          {frame}
          {maskCanvas}
        </div>
        {actions}
        <p className="seed-hint seed-hint--docked">
          Eszközök a képkocka felett · festés a képen · Varázsceruza = flood-fill kattintásra
        </p>
      </div>
    );
  }

  return (
    <div className="seed-paint">
      {tools}
      <div className="seed-stage">
        <canvas ref={bgRef} className="seed-bg" />
        {maskCanvas}
      </div>
      {actions}
      <p className="seed-hint">
        Forrás a maszk alatt. A kézi maszk scrub után is megmarad. Export → Max minőség /
        MatAnyone2.
      </p>
    </div>
  );
}
