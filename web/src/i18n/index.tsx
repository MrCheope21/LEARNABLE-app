import { useQuery } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { auth } from "../api/endpoints";
import { useAuth } from "../auth/AuthContext";
import { en, type MessageKey, type Messages } from "./messages/en";

/** The interface languages, each named in its own language. Codes match the API's. */
export const LANGUAGES = [
  { code: "en", name: "English" },
  { code: "it", name: "Italiano" },
  { code: "es", name: "Español" },
  { code: "fr", name: "Français" },
  { code: "de", name: "Deutsch" },
  { code: "zh", name: "中文（简体）" },
  { code: "ja", name: "日本語" },
  { code: "ar", name: "العربية" },
  { code: "hi", name: "हिन्दी" },
] as const;
export type Language = (typeof LANGUAGES)[number]["code"];

// English ships with the app; every other language is fetched when it is first needed, so a
// phone downloads one catalog instead of nine.
const CATALOGS: Partial<Record<Language, Messages>> = { en };
const LOADERS: Record<Exclude<Language, "en">, () => Promise<Messages>> = {
  it: () => import("./messages/it").then((m) => m.it),
  es: () => import("./messages/es").then((m) => m.es),
  fr: () => import("./messages/fr").then((m) => m.fr),
  de: () => import("./messages/de").then((m) => m.de),
  zh: () => import("./messages/zh").then((m) => m.zh),
  ja: () => import("./messages/ja").then((m) => m.ja),
  ar: () => import("./messages/ar").then((m) => m.ar),
  hi: () => import("./messages/hi").then((m) => m.hi),
};

/** Fetches a language's texts (once). Until then its texts show in English. */
export async function loadCatalog(language: Language): Promise<void> {
  if (language === "en" || CATALOGS[language]) return;
  CATALOGS[language] = await LOADERS[language]();
}

/** Tests: every language at once. */
export async function loadAllCatalogs(): Promise<void> {
  await Promise.all(LANGUAGES.map((l) => loadCatalog(l.code)));
}
const RIGHT_TO_LEFT: ReadonlySet<Language> = new Set(["ar"]);
const STORAGE_KEY = "learnable.language";

function isLanguage(value: unknown): value is Language {
  return typeof value === "string" && LANGUAGES.some((l) => l.code === value);
}

/** Before sign-in: the last language used in this browser, else the browser's own, else English. */
export function detectLanguage(): Language {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (isLanguage(stored)) return stored;
  } catch {
    // Storage blocked: fall through to the browser's languages.
  }
  for (const tag of navigator.languages ?? [navigator.language]) {
    const code = tag.slice(0, 2).toLowerCase();
    if (isLanguage(code)) return code;
  }
  return "en";
}

export function translate(language: Language, key: MessageKey, vars?: Record<string, string | number>): string {
  const text = CATALOGS[language]?.[key] ?? en[key];
  return vars ? text.replace(/\{(\w+)\}/g, (match, name: string) => (name in vars ? String(vars[name]) : match)) : text;
}

type I18n = {
  language: Language;
  dir: "ltr" | "rtl";
  /** Changes the language for this browser; signed-in pages also save it to the account. */
  setLocalLanguage: (language: Language) => void;
  t: (key: MessageKey, vars?: Record<string, string | number>) => string;
};

const I18nContext = createContext<I18n>({
  language: "en",
  dir: "ltr",
  setLocalLanguage: () => undefined,
  t: (key, vars) => translate("en", key, vars),
});

/**
 * The interface language: the account's when signed in (so it follows the user to every device),
 * otherwise the one chosen or detected in this browser. Sets <html lang> and <html dir>.
 */
export function I18nProvider({ children }: { children: ReactNode }) {
  const { isSignedIn } = useAuth();
  // Same key as AppShell's meKey (not imported: AppShell depends on this module).
  const me = useQuery({ queryKey: ["me"], queryFn: auth.me, enabled: isSignedIn, retry: false });
  const [local, setLocal] = useState<Language>(detectLanguage);
  const account = isSignedIn ? me.data?.language : undefined;
  const language: Language = isLanguage(account) ? account : local;
  const dir = RIGHT_TO_LEFT.has(language) ? "rtl" : "ltr";

  useEffect(() => {
    document.documentElement.lang = language;
    document.documentElement.dir = dir;
    try {
      localStorage.setItem(STORAGE_KEY, language);
    } catch {
      // Not remembered for the sign-in page; everything else still works.
    }
  }, [language, dir]);

  // Counts the catalogs that arrived, so texts are read again once the language's own is there.
  const [loaded, setLoaded] = useState(0);
  useEffect(() => {
    if (CATALOGS[language]) return;
    let live = true;
    void loadCatalog(language).then(
      () => live && setLoaded((n) => n + 1),
      () => undefined, // offline: English until the next visit
    );
    return () => {
      live = false;
    };
  }, [language]);

  const t = useCallback(
    (key: MessageKey, vars?: Record<string, string | number>) => translate(language, key, vars),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `loaded` changes what translate() finds
    [language, loaded],
  );
  const value = useMemo(() => ({ language, dir, setLocalLanguage: setLocal, t }) satisfies I18n, [language, dir, t]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18n {
  return useContext(I18nContext);
}
