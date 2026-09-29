// Writes the static identity files from src/brand/geometry.ts:
//   public/favicon.svg, public/app-icon.svg        (the active concept)
//   public/brand/<concept>-<form>-<tone>.svg        (both concepts, for docs and other clients)
// Run: node scripts/export-brand.ts   (Node 22.18+/24 strips the types itself)
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { ACTIVE_CONCEPT } from "../src/brand/active.ts";
import { BRAND_BLUE, appIcon, mark, standalone, wordmark, type Concept } from "../src/brand/geometry.ts";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "public");
const brandDir = join(root, "brand");
mkdirSync(brandDir, { recursive: true });

const tones: Record<string, string> = { blue: BRAND_BLUE, white: "#FFFFFF", mono: "#111111" };
const concepts: Concept[] = ["concept5", "concept3"];

for (const concept of concepts) {
  for (const [tone, color] of Object.entries(tones)) {
    writeFileSync(join(brandDir, `${concept}-wordmark-${tone}.svg`), standalone(wordmark(concept), color, "learnable") + "\n");
    writeFileSync(join(brandDir, `${concept}-mark-${tone}.svg`), standalone(mark(concept), color, "learnable") + "\n");
  }
  writeFileSync(join(brandDir, `${concept}-app-icon.svg`), appIcon(concept) + "\n");
}
writeFileSync(join(root, "favicon.svg"), appIcon(ACTIVE_CONCEPT) + "\n");
writeFileSync(join(root, "app-icon.svg"), appIcon(ACTIVE_CONCEPT) + "\n");
console.log(`brand assets written (active: ${ACTIVE_CONCEPT})`);
