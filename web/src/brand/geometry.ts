// LEARNABLE identity geometry: every mark is drawn from strokes (no font, no raster), so it is
// identical everywhere and stays crisp at any size. Shared by the React BrandLogo and by
// scripts/export-brand.ts, which writes the static SVG files (favicon, app icon, docs).
//
// Letter grid (stroke centerlines): baseline y=38, x-height y=14, ascender y=3, stroke 6 with
// round caps, so the outer edges are baseline 41, x-height 11, ascender 0.

export const BRAND_BLUE = "#1555DD";
export const STROKE = 6;

export type Concept = "concept5" | "concept3";

interface Glyph {
  width: number;
  paths: string[];
}

// A full circle of radius 12 whose left edge is at x = left.
const BOWL = (left: number) =>
  `M${left + 24},26 A12,12 0 1 1 ${left},26 A12,12 0 1 1 ${left + 24},26`;

const GLYPHS: Record<string, Glyph> = {
  l: { width: 6, paths: ["M3,3 V38"] },
  e: { width: 30, paths: ["M3.5,26 H27 A12,12 0 1 0 23.5,34.5"] },
  r: { width: 20, paths: ["M3,14 V38", "M3,25 A11,11 0 0 1 14,14 H17"] },
  n: { width: 26, paths: ["M3,14 V38", "M3,25 A10,10 0 0 1 23,25 V38"] },
  b: { width: 30, paths: ["M3,3 V38", BOWL(3)] },
  // Concept 3: a plain single-storey a (full bowl and stem).
  a: { width: 30, paths: [BOWL(3), "M27,14 V38"] },
  // Concept 5: the bowl is an open loop that starts clear of the stem, circles round and
  // returns into it, like a "go round again" arrow: recall. Closed at the bottom and joined to
  // the stem, so it still reads instantly as an "a".
  a5: { width: 31, paths: ["M17.6,14.7 A12,12 0 1 0 24.4,32", "M28,14 V38"] },
};

const GAP = 4;

function word(letters: string[]): { width: number; paths: string[] } {
  let x = 0;
  const paths: string[] = [];
  letters.forEach((key, index) => {
    const glyph = GLYPHS[key];
    if (!glyph) throw new Error(`no glyph ${key}`);
    for (const d of glyph.paths) paths.push(`<path transform="translate(${x} 0)" d="${d}"/>`);
    x += glyph.width + (index < letters.length - 1 ? GAP : 0);
  });
  return { width: x, paths };
}

const WORDMARK_LETTERS: Record<Concept, string[]> = {
  concept5: ["l", "e", "a5", "r", "n", "a5", "b", "l", "e"],
  concept3: ["l", "e", "a", "r", "n", "a", "b", "l", "e"],
};

// Concept 3, "pages in motion": an open book whose right page rises into an upward stroke.
// 48 x 44 box, same stroke weight as the letters.
const BOOK = [
  // left page
  "M24,40 C18,36.5 10,36 3,37.5 V8.5 C10,7 18,7.5 24,11 Z",
  // right page, its outer edge lifting past the book into the upward stroke
  "M24,40 C30,36.5 38,36 45,37.5 V13",
  "M24,11 C29,8 34,6.5 38,6 L45,3",
];

export interface Artwork {
  viewBox: string;
  width: number;
  height: number;
  // Inner SVG markup: stroked paths (fill none) using the given color.
  body: (color: string) => string;
}

function stroked(paths: string[], color: string, extra = ""): string {
  return (
    `<g fill="none" stroke="${color}" stroke-width="${STROKE}" stroke-linecap="round" ` +
    `stroke-linejoin="round"${extra}>${paths.join("")}</g>`
  );
}

/** The horizontal wordmark (concept 3 adds its book symbol before the word). */
export function wordmark(concept: Concept): Artwork {
  const letters = word(WORDMARK_LETTERS[concept]);
  if (concept === "concept5") {
    const pad = 3;
    const width = letters.width + pad * 2;
    return {
      viewBox: `${-pad} ${-pad} ${width} 47`,
      width,
      height: 47,
      body: (color) => stroked(letters.paths, color),
    };
  }
  const bookPaths = BOOK.map((d) => `<path d="${d}"/>`);
  const shift = 60;
  const width = shift + letters.width + 6;
  return {
    viewBox: `-3 -3 ${width} 47`,
    width,
    height: 47,
    body: (color) =>
      stroked(bookPaths, color) + stroked(letters.paths, color, ` transform="translate(${shift} 0)"`),
  };
}

/** The compact mark, used alone as the app icon: concept 5's "a", concept 3's book. */
export function mark(concept: Concept): Artwork {
  if (concept === "concept5") {
    const [loop = "", stem = ""] = GLYPHS.a5?.paths ?? [];
    return {
      viewBox: "-5 5 40 40",
      width: 40,
      height: 40,
      body: (color) => stroked([`<path d="${loop}"/>`, `<path d="${stem}"/>`], color),
    };
  }
  return {
    viewBox: "-4 -4 56 52",
    width: 56,
    height: 52,
    body: (color) => stroked(BOOK.map((d) => `<path d="${d}"/>`), color),
  };
}

/** A square app icon: the mark in white on the brand blue, rounded corners. */
export function appIcon(concept: Concept): string {
  const inner = mark(concept);
  const [minX, minY, w, h] = inner.viewBox.split(" ").map(Number) as [number, number, number, number];
  const size = 64;
  const scale = 40 / Math.max(w, h);
  const offsetX = (size - w * scale) / 2 - minX * scale;
  const offsetY = (size - h * scale) / 2 - minY * scale;
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${size} ${size}">` +
    `<rect width="${size}" height="${size}" rx="14" fill="${BRAND_BLUE}"/>` +
    `<g transform="translate(${offsetX.toFixed(2)} ${offsetY.toFixed(2)}) scale(${scale.toFixed(4)})">` +
    inner.body("#FFFFFF") +
    `</g></svg>`
  );
}

export function standalone(art: Artwork, color: string, title: string): string {
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${art.viewBox}" role="img">` +
    `<title>${title}</title>${art.body(color)}</svg>`
  );
}
