import { useEffect, useState } from "react";

/**
 * Installing LEARNABLE as an app (a "progressive web app"): the same site, opened from an icon
 * on the home screen, full screen, and able to open without a network.
 *
 * Android and desktop Chrome/Edge offer an install prompt the page can trigger; iPhone and iPad
 * have no such prompt: the person uses Share → "Add to Home Screen" in Safari.
 */

type InstallPromptEvent = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: "accepted" | "dismissed" }> };

let deferred: InstallPromptEvent | null = null;
const listeners = new Set<() => void>();
const changed = () => listeners.forEach((listener) => listener());

if (typeof window !== "undefined") {
  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault(); // keep it for our own button instead of the browser's banner
    deferred = event as InstallPromptEvent;
    changed();
  });
  window.addEventListener("appinstalled", () => {
    deferred = null;
    changed();
  });
}

/** Only in the built app: in development a service worker would serve stale files. */
export function registerServiceWorker(): void {
  if (!import.meta.env.PROD || !("serviceWorker" in navigator)) return;
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {
      // Not installable then (private browsing, an old browser): the site works as before.
    });
  });
}

export function isStandalone(): boolean {
  if (typeof window === "undefined") return false;
  const iosStandalone = (navigator as Navigator & { standalone?: boolean }).standalone === true;
  return iosStandalone || (typeof window.matchMedia === "function" && window.matchMedia("(display-mode: standalone)").matches);
}

export type Platform = "ios" | "android" | "desktop";

export function platform(): Platform {
  const agent = navigator.userAgent;
  // iPadOS says it is a Mac; a Mac has no touch screen.
  if (/iPhone|iPad|iPod/.test(agent) || (/Macintosh/.test(agent) && navigator.maxTouchPoints > 1)) return "ios";
  if (/Android/.test(agent)) return "android";
  return "desktop";
}

/** Whether the browser offered an install prompt, and a function to show it. */
export function useInstallPrompt(): { canPrompt: boolean; install: () => Promise<boolean> } {
  const [, refresh] = useState(0);
  useEffect(() => {
    const listener = () => refresh((n) => n + 1);
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  }, []);
  return {
    canPrompt: deferred !== null,
    install: async () => {
      if (!deferred) return false;
      const event = deferred;
      await event.prompt();
      const { outcome } = await event.userChoice;
      deferred = null;
      changed();
      return outcome === "accepted";
    },
  };
}

/** True while the browser reports no network. */
export function useOffline(): boolean {
  const [offline, setOffline] = useState(() => typeof navigator !== "undefined" && navigator.onLine === false);
  useEffect(() => {
    const on = () => setOffline(false);
    const off = () => setOffline(true);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => {
      window.removeEventListener("online", on);
      window.removeEventListener("offline", off);
    };
  }, []);
  return offline;
}
