import { describe, expect, it } from "vitest";
import { ar } from "./messages/ar";
import { de } from "./messages/de";
import { en } from "./messages/en";
import { es } from "./messages/es";
import { fr } from "./messages/fr";
import { hi } from "./messages/hi";
import { it as italian } from "./messages/it";
import { ja } from "./messages/ja";
import { zh } from "./messages/zh";

const catalogs: Record<string, Record<string, string>> = { it: italian, es, fr, de, zh, ja, ar, hi };
const placeholders = (text: string) => [...text.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();

// Letters each language's texts must use (a text pasted into the wrong language is caught).
const SCRIPT: Record<string, RegExp> = {
  zh: /[一-鿿]/,
  ja: /[぀-ヿ一-鿿]/,
  ar: /[؀-ۿ]/,
  hi: /[ऀ-ॿ]/,
};
// Short texts that are legitimately the same in every language (names, symbols, units).
const NEUTRAL = /^[\s\d+\-–—·:/()~%#.,…✓×🛒🏆📖XP：，、。；（）「」،]*$/u;
// Texts that are written the same way in several languages (e.g. "Q&A" in Japanese).
const SAME_OK = new Set(["mat.qa"]);
const bare = (text: string) => text.replace(/\{\w+\}/g, "");

describe("interface catalogs", () => {
  const keys = Object.keys(en);

  for (const [lang, catalog] of Object.entries(catalogs)) {
    it(`${lang} has every text, with the same placeholders`, () => {
      const missing = keys.filter((k) => !(k in catalog));
      expect(missing).toEqual([]);
      const extra = Object.keys(catalog).filter((k) => !(k in en));
      expect(extra).toEqual([]);
      const mismatched = keys.filter((k) => JSON.stringify(placeholders(catalog[k] ?? "")) !== JSON.stringify(placeholders(en[k as keyof typeof en])));
      expect(mismatched).toEqual([]);
    });

    it(`${lang} has no empty text`, () => {
      expect(keys.filter((k) => !(catalog[k] ?? "").trim())).toEqual([]);
    });

    const script = SCRIPT[lang];
    if (script) {
      it(`${lang} texts are written in its own script`, () => {
        const wrong = keys.filter((k) => !SAME_OK.has(k) && !NEUTRAL.test(bare(catalog[k] ?? "")) && !script.test(catalog[k] ?? ""));
        expect(wrong).toEqual([]);
        // The text must not be the English one left in place (apart from neutral ones).
        const untranslated = keys.filter((k) => !SAME_OK.has(k) && catalog[k] === en[k as keyof typeof en] && !NEUTRAL.test(bare(catalog[k] ?? "")));
        expect(untranslated).toEqual([]);
      });
    }
  }

  it("does not leave Latin-script languages with English in place", () => {
    const allowedSame = new Set(["community.title", "nav.community", "nav.marketplace"]);
    for (const lang of ["it", "es", "fr", "de"] as const) {
      const catalog = catalogs[lang]!;
      const same = keys.filter((k) => catalog[k] === en[k as keyof typeof en] && !NEUTRAL.test(bare(catalog[k] ?? "")) && !allowedSame.has(k));
      // A few words are the same in a language (e.g. "Menu", "Extra"): keep the list short.
      expect(same.length, `${lang}: ${same.slice(0, 12).join(", ")}`).toBeLessThan(40);
    }
  });
});
