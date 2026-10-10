import { useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { useI18n } from "../i18n";

type Point = { x: number; y: number };
type Stroke = { points: Point[]; eraser: boolean; width: number };

const WIDTH = 900;
const HEIGHT = 600;
const PEN = "#1b1f27";
// Photos are shrunk before upload: enough detail for a structure, a fraction of the size.
const MAX_PHOTO_SIDE = 1600;

/**
 * Where a drawn answer is made: pen, eraser, undo and clear, with mouse, finger or stylus. Or a
 * photo of a drawing made on paper. Reports a PNG/JPEG data URL, or null while empty.
 */
export function DrawingPad({ onChange, disabled = false }: { onChange: (dataUrl: string | null) => void; disabled?: boolean }) {
  const { t } = useI18n();
  const canvas = useRef<HTMLCanvasElement>(null);
  const [strokes, setStrokes] = useState<Stroke[]>([]);
  const [eraser, setEraser] = useState(false);
  const [thick, setThick] = useState(false);
  const [photo, setPhoto] = useState<string | null>(null);
  const [photoError, setPhotoError] = useState<string | null>(null);
  const drawing = useRef<Stroke | null>(null);

  const paint = useCallback((list: Stroke[]) => {
    const ctx = canvas.current?.getContext("2d");
    if (!ctx) return;
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, WIDTH, HEIGHT);
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    for (const stroke of list) {
      ctx.strokeStyle = stroke.eraser ? "#ffffff" : PEN;
      ctx.lineWidth = stroke.width;
      ctx.beginPath();
      stroke.points.forEach((p, i) => (i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y)));
      if (stroke.points.length === 1) ctx.lineTo(stroke.points[0]!.x + 0.1, stroke.points[0]!.y);
      ctx.stroke();
    }
  }, []);

  useEffect(() => paint(strokes), [paint, strokes]);

  const report = (list: Stroke[]) => {
    const hasInk = list.some((s) => !s.eraser);
    onChange(hasInk && canvas.current ? canvas.current.toDataURL("image/png") : null);
  };

  const point = (event: ReactPointerEvent<HTMLCanvasElement>): Point => {
    const box = event.currentTarget.getBoundingClientRect();
    return { x: ((event.clientX - box.left) / box.width) * WIDTH, y: ((event.clientY - box.top) / box.height) * HEIGHT };
  };

  const down = (event: ReactPointerEvent<HTMLCanvasElement>) => {
    if (disabled) return;
    event.currentTarget.setPointerCapture?.(event.pointerId);
    drawing.current = { points: [point(event)], eraser, width: eraser ? 28 : thick ? 9 : 4 };
    paint([...strokes, drawing.current]);
  };
  const move = (event: ReactPointerEvent<HTMLCanvasElement>) => {
    if (!drawing.current) return;
    drawing.current.points.push(point(event));
    paint([...strokes, drawing.current]);
  };
  const up = () => {
    if (!drawing.current) return;
    const next = [...strokes, drawing.current];
    drawing.current = null;
    setStrokes(next);
    paint(next);
    report(next);
  };

  const undo = () => {
    const next = strokes.slice(0, -1);
    setStrokes(next);
    paint(next);
    report(next);
  };
  const clear = () => {
    setStrokes([]);
    paint([]);
    onChange(null);
  };

  const takePhoto = async (file: File) => {
    setPhotoError(null);
    try {
      const url = await shrink(file);
      setPhoto(url);
      onChange(url);
    } catch {
      setPhotoError(t("drawing.photoError"));
    }
  };

  if (photo) {
    return (
      <div className="drawing-pad">
        <img src={photo} alt={t("drawing.photoAlt")} className="drawing-photo" />
        <div className="drawing-tools">
          <button
            type="button"
            disabled={disabled}
            onClick={() => {
              setPhoto(null);
              report(strokes);
            }}
          >
            {t("drawing.drawInstead")}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="drawing-pad">
      <div className="drawing-tools" role="toolbar" aria-label={t("drawing.tools")}>
        <button type="button" aria-pressed={!eraser} disabled={disabled} onClick={() => setEraser(false)}>
          {t("drawing.pen")}
        </button>
        <button type="button" aria-pressed={eraser} disabled={disabled} onClick={() => setEraser(true)}>
          {t("drawing.eraser")}
        </button>
        <button type="button" aria-pressed={thick} disabled={disabled || eraser} onClick={() => setThick((v) => !v)}>
          {thick ? t("drawing.thick") : t("drawing.thin")}
        </button>
        <button type="button" disabled={disabled || strokes.length === 0} onClick={undo}>
          {t("drawing.undo")}
        </button>
        <button type="button" className="link danger" disabled={disabled || strokes.length === 0} onClick={clear}>
          {t("drawing.clear")}
        </button>
      </div>
      <canvas
        ref={canvas}
        width={WIDTH}
        height={HEIGHT}
        className="drawing-canvas"
        role="img"
        aria-label={t("drawing.area")}
        onPointerDown={down}
        onPointerMove={move}
        onPointerUp={up}
        onPointerCancel={up}
        onPointerLeave={up}
      />
      <label className="drawing-upload">
        {t("drawing.photoUpload")}
        <input
          type="file"
          accept="image/*"
          capture="environment"
          disabled={disabled}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void takePhoto(file);
            e.target.value = "";
          }}
        />
      </label>
      {photoError && (
        <p className="banner warning" role="alert">
          {photoError}
        </p>
      )}
    </div>
  );
}

/** A photo, scaled down to MAX_PHOTO_SIDE and re-encoded as JPEG (also drops its metadata). */
async function shrink(file: File): Promise<string> {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, MAX_PHOTO_SIDE / Math.max(bitmap.width, bitmap.height));
  const out = document.createElement("canvas");
  out.width = Math.round(bitmap.width * scale);
  out.height = Math.round(bitmap.height * scale);
  const ctx = out.getContext("2d");
  if (!ctx) throw new Error("no canvas");
  ctx.drawImage(bitmap, 0, 0, out.width, out.height);
  return out.toDataURL("image/jpeg", 0.85);
}

/** A data URL as a file, to upload a drawing made on the pad. */
export function dataUrlToBlob(dataUrl: string): Blob {
  const [head, data = ""] = dataUrl.split(",");
  const type = /data:([^;]+)/.exec(head ?? "")?.[1] ?? "image/png";
  const bytes = Uint8Array.from(atob(data), (c) => c.charCodeAt(0));
  return new Blob([bytes], { type });
}
