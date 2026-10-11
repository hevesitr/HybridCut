import { useEffect, useRef, useState, type ReactNode } from "react";

type Tool = "brush" | "erase" | "lasso" | "wand";

export type WandPickResult = {
  ok: boolean;
  pngB64?: string | null;
  message: string;
  part?: string | null;
  labelHu?: string | null;
};

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
  /** Selected timeline clip — wand/seed apply to this clip's mask. */
  selectedClipId?: string | null;
  /**
   * Varázsceruza part-pick (face-only). Normalized coords in source frame space.
   * When omitted, falls back to local colour flood (legacy).
   */
  onWandPick?: (args: {
    xNorm: number;
    yNorm: number;
    erase: boolean;
  }) => Promise<WandPickResult>;
  /** Fires when a paint stroke is actively capturing the pointer (timeline must ignore). */
  onPaintGesture?: (active: boolean) => void;
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

/** Chebyshev + light luminance — matches slider "tűrés" better than Euclidean RGB. */
function colorClose(
  r0: number,
  g0: number,
  b0: number,
  r1: number,
  g1: number,
  b1: number,
  tolerance: number,
) {
  const dr = Math.abs(r0 - r1);
  const dg = Math.abs(g0 - g1);
  const db = Math.abs(b0 - b1);
  if (Math.max(dr, dg, db) > tolerance) return false;
  // Soft luminance gate so JPEG chroma noise doesn't leak across edges.
  const y0 = 0.299 * r0 + 0.587 * g0 + 0.114 * b0;
  const y1 = 0.299 * r1 + 0.587 * g1 + 0.114 * b1;
  return Math.abs(y0 - y1) <= tolerance * 1.15;
}

/**
 * Scanline flood-fill on mask from reference RGB (legacy / offline fallback).
 * Primary Varázsceruza path is server face/region part-pick.
 */
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
  const match = (x: number, y: number) => {
    const pi = (y * w + x) * 4;
    return colorClose(rd[pi], rd[pi + 1], rd[pi + 2], tr, tg, tb, tolerance);
  };
  const visited = new Uint8Array(w * h);
  const stack: number[] = [x0, y0];
  let painted = 0;
  // Tight cap — face/part only; whole-person flood is the bug we avoid.
  const maxPaint = Math.floor(w * h * 0.12);

  const paintPx = (pi: number) => {
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
  };

  while (stack.length && painted < maxPaint) {
    const y = stack.pop()!;
    let x = stack.pop()!;
    if (y < 0 || y >= h) continue;
    while (x >= 0 && !visited[y * w + x] && match(x, y)) x -= 1;
    x += 1;
    let spanUp = false;
    let spanDown = false;
    while (x < w && !visited[y * w + x] && match(x, y)) {
      const idx = y * w + x;
      visited[idx] = 1;
      paintPx(idx * 4);
      painted += 1;
      if (painted >= maxPaint) break;
      if (y > 0) {
        const up = (y - 1) * w + x;
        if (!visited[up] && match(x, y - 1)) {
          if (!spanUp) {
            stack.push(x, y - 1);
            spanUp = true;
          }
        } else spanUp = false;
      }
      if (y + 1 < h) {
        const dn = (y + 1) * w + x;
        if (!visited[dn] && match(x, y + 1)) {
          if (!spanDown) {
            stack.push(x, y + 1);
            spanDown = true;
          }
        } else spanDown = false;
      }
      x += 1;
    }
  }
  maskCtx.putImageData(mask, 0, 0);
  return painted;
}

function insideMaskSurface(
  e: { clientX: number; clientY: number },
  canvas: HTMLCanvasElement,
  pad = 2,
) {
  const rect = canvas.getBoundingClientRect();
  return (
    e.clientX >= rect.left - pad &&
    e.clientX <= rect.right + pad &&
    e.clientY >= rect.top - pad &&
    e.clientY <= rect.bottom + pad
  );
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
  selectedClipId = null,
  onWandPick,
  onPaintGesture,
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
  const [wandTol, setWandTol] = useState(40);
  const [wandMsg, setWandMsg] = useState<string | null>(null);
  const [paintingUi, setPaintingUi] = useState(false);
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

  const setGesture = (active: boolean) => {
    setPaintingUi(active);
    onPaintGesture?.(active);
  };

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
        mask.style.right = "auto";
        mask.style.bottom = "auto";
        mask.style.transform = "none";
        return;
      }
      imgProbeRef.current = img;
      const wr = wrap.getBoundingClientRect();
      const ir = img.getBoundingClientRect();
      if (wr.width < 1 || wr.height < 1) return;
      // Never let the mask hit-target spill outside the preview frame (timeline bleed).
      const left = Math.max(0, ir.left - wr.left);
      const top = Math.max(0, ir.top - wr.top);
      const widthPx = Math.min(ir.width, wr.width - left);
      const heightPx = Math.min(ir.height, wr.height - top);
      mask.style.position = "absolute";
      mask.style.left = `${left}px`;
      mask.style.top = `${top}px`;
      mask.style.width = `${Math.max(1, widthPx)}px`;
      mask.style.height = `${Math.max(1, heightPx)}px`;
      mask.style.right = "auto";
      mask.style.bottom = "auto";
      mask.style.inset = "auto";
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

  // Background / reference RGB for wand fallback + panel mode
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

  // Bind server seed once per mask payload / selected clip (survives scrub)
  useEffect(() => {
    const mask = maskRef.current;
    if (!mask) return;
    const ctx = mask.getContext("2d");
    if (!ctx) return;
    const key = `${selectedClipId || ""}::${initialMaskPngB64 || ""}`;
    if (!initialMaskPngB64) {
      if (lastMaskKey.current) {
        ctx.clearRect(0, 0, mask.width, mask.height);
        lastMaskKey.current = null;
      }
      return;
    }
    if (lastMaskKey.current === key) return;
    lastMaskKey.current = key;
    void drawMaskFromPng(ctx, initialMaskPngB64, mask.width || w, mask.height || h);
  }, [initialMaskPngB64, selectedClipId, w, h]);

  // Clear local mask when switching active clip so wand does not bleed across clips
  useEffect(() => {
    lastMaskKey.current = null;
    setWandMsg(null);
  }, [selectedClipId]);

  const pos = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const canvas = maskRef.current!;
    const rect = canvas.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / Math.max(1, rect.width)) * canvas.width;
    const y = ((e.clientY - rect.top) / Math.max(1, rect.height)) * canvas.height;
    return {
      x: Math.max(0, Math.min(canvas.width, x)),
      y: Math.max(0, Math.min(canvas.height, y)),
      xNorm: Math.max(0, Math.min(1, (e.clientX - rect.left) / Math.max(1, rect.width))),
      yNorm: Math.max(0, Math.min(1, (e.clientY - rect.top) / Math.max(1, rect.height))),
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
    setGesture(false);
  };

  const paintAt = (x: number, y: number) => {
    const canvas = maskRef.current;
    const ctx = canvas?.getContext("2d");
    if (!ctx || !canvas) return;
    // Hard clamp — never paint outside mask bitmap (timeline coords map off-canvas).
    if (x < -brush || y < -brush || x > canvas.width + brush || y > canvas.height + brush) {
      return;
    }
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
    // Paint surface only — never let the gesture reach the timeline dock.
    e.preventDefault();
    e.stopPropagation();
    try {
      e.currentTarget.setPointerCapture(e.pointerId);
      pointerId.current = e.pointerId;
    } catch {
      pointerId.current = e.pointerId;
    }
    setGesture(true);
    const { x, y, xNorm, yNorm } = pos(e);

    if (tool === "wand") {
      const erase = e.altKey || e.button === 2;
      drawing.current = false;
      const run = async () => {
        if (onWandPick) {
          setWandMsg("Varázsceruza: rész kijelölése…");
          try {
            const res = await onWandPick({ xNorm, yNorm, erase });
            setWandMsg(res.message);
            if (res.ok && res.pngB64) {
              const ctx = maskRef.current?.getContext("2d");
              if (ctx && maskRef.current) {
                await drawMaskFromPng(
                  ctx,
                  res.pngB64,
                  maskRef.current.width || w,
                  maskRef.current.height || h,
                );
                lastMaskKey.current = res.pngB64;
                dirty.current = false;
              }
            }
          } catch (err) {
            setWandMsg(err instanceof Error ? err.message : "Varázsceruza hiba");
          } finally {
            releasePointer(e.currentTarget);
          }
          return;
        }
        // Offline fallback — constrained colour flood
        const ref = refRgb.current;
        const ctx = maskRef.current?.getContext("2d");
        if (ref && ctx) {
          const n = floodFillMask(ctx, ref, x, y, wandTol, erase);
          dirty.current = n > 0;
          setWandMsg(
            n > 0
              ? `Varázsceruza (helyi): ${n.toLocaleString("hu-HU")} px${erase ? " törölve" : ""}`
              : "Varázsceruza: nincs találat — növeld a tűrést",
          );
          if (n > 0 && autoCommitOnStrokeEnd) commit();
        } else {
          setWandMsg("Varázsceruza: várj a képkockára…");
        }
        releasePointer(e.currentTarget);
      };
      void run();
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
    e.stopPropagation();
    // If the pointer left the mask surface (e.g. over timeline), stop painting
    // and release capture so the timeline can receive the next gesture.
    if (!insideMaskSurface(e, e.currentTarget, 4)) {
      endStroke(e.currentTarget);
      return;
    }
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
    e.stopPropagation();
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
    setWandMsg(null);
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
        title="Radír: téves maszkterület törlése — csak az előnézet maszkon, nem az idővonalon."
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
        title="Varázsceruza: kattints az arcra — csak az arc (rész) kerül a nobg alphába. Alt+katt = törlés."
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
      {tool === "wand" && !onWandPick ? (
        <label className="brush-size" title="Varázsceruza tűrése (helyi fallback).">
          Tűrés
          <input
            type="range"
            min={6}
            max={96}
            value={wandTol}
            disabled={disabled}
            onChange={(e) => setWandTol(Number(e.target.value))}
          />
          <span>{wandTol}</span>
        </label>
      ) : null}
      {wandMsg ? (
        <span className="wand-msg" title={wandMsg}>
          {wandMsg}
        </span>
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
      className={`seed-mask${disabled ? " seed-mask--passthrough" : ""}`}
      data-paint-surface="1"
      data-paint-tool={tool}
      style={disabled ? { pointerEvents: "none" } : undefined}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerCancel}
      onContextMenu={(e) => e.preventDefault()}
      title={
        disabled
          ? "Mozgatás be — festés szünetel (kapcsold ki a Mozgatást a festéshez)"
          : tool === "wand"
            ? "Varázsceruza — kattints az arcra (csak arc nobg)"
            : tool === "erase"
              ? "Radír — csak az előnézet maszkon"
              : "Fesd a kézi maszkot a forrás képkockára."
      }
    />
  );

  if (docked) {
    return (
      <div
        className={`seed-paint seed-paint--docked${paintingUi ? " seed-painting" : ""}`}
        data-paint-tool={tool}
      >
        {tools}
        <div className="seed-frame" ref={frameWrapRef}>
          {frame}
          {maskCanvas}
        </div>
        {actions}
        <p className="seed-hint seed-hint--docked">
          Ecset / Radír csak az előnézeten · Varázsceruza = arc / rész → átlátszó nobg
        </p>
      </div>
    );
  }

  return (
    <div className={`seed-paint${paintingUi ? " seed-painting" : ""}`} data-paint-tool={tool}>
      {tools}
      <div className="seed-stage">
        <canvas ref={bgRef} className="seed-bg" />
        {maskCanvas}
      </div>
      {actions}
      <p className="seed-hint">
        Forrás a maszk alatt. Varázsceruza = arc-only nobg. Export → Max minőség.
      </p>
    </div>
  );
}
