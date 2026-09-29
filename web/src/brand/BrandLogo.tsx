import { ACTIVE_CONCEPT } from "./active.ts";
import { BRAND_BLUE, mark, wordmark, type Concept } from "./geometry.ts";

type Tone = "blue" | "white" | "mono";

const COLORS: Record<Tone, string> = { blue: BRAND_BLUE, white: "#FFFFFF", mono: "currentColor" };

/**
 * The LEARNABLE identity, drawn as inline SVG from src/brand/geometry.ts (no font, no image
 * request). `form`: the horizontal wordmark or the compact mark. `tone`: blue on light
 * backgrounds, white on the blue navigation, mono inherits the text color.
 * Decorative by default (the surrounding link names it); pass `label` to make it an image.
 */
export function BrandLogo({
  form = "wordmark",
  tone = "blue",
  height = 28,
  label,
  concept = ACTIVE_CONCEPT,
}: {
  form?: "wordmark" | "mark";
  tone?: Tone;
  height?: number;
  label?: string;
  concept?: Concept;
}) {
  const art = form === "wordmark" ? wordmark(concept) : mark(concept);
  const width = (height * art.width) / art.height;
  return (
    <svg
      className={`brand-logo brand-${form}`}
      viewBox={art.viewBox}
      width={Math.round(width)}
      height={height}
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      focusable="false"
      // Static artwork from our own constants, never user data.
      dangerouslySetInnerHTML={{ __html: art.body(COLORS[tone]) }}
    />
  );
}
