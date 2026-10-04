import { useQuery } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { auth } from "../api/endpoints";
import { useAuth } from "../auth/AuthContext";
import { ar } from "./messages/ar";
import { de } from "./messages/de";
import { en, type MessageKey, type Messages } from "./messages/en";
import { es } from "./messages/es";
import { fr } from "./messages/fr";
import { hi } from "./messages/hi";
import { it } from "./messages/it";
import { ja } from "./messages/ja";
import { zh } from "./messages/zh";

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

const CATALOGS: Record<Language, Messages> = { en, it, es, fr, de, zh, ja, ar, hi };
const RIGHT_TO_LEFT: ReadonlySet<Language> = new Set(["ar"]);
const STORAGE_KEY = "learnable.language";

function isLanguage(value: unknown): value is Language {
  return typeof value === "string" && value in CATALOGS;
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
  const text = CATALOGS[language][key] ?? en[key];
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

  const t = useCallback((key: MessageKey, vars?: Record<string, string | number>) => translate(language, key, vars), [language]);
  const value = useMemo(() => ({ language, dir, setLocalLanguage: setLocal, t }) satisfies I18n, [language, dir, t]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18n {
  return useContext(I18nContext);
}
