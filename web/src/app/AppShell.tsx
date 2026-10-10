import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useId, useMemo, useRef, useState, type FormEvent } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";
import { auth, dashboard } from "../api/endpoints";
import { useAuth } from "../auth/AuthContext";
import { BrandLogo } from "../brand/BrandLogo";
import { ErrorBanner } from "../components/QueryState";
import { useI18n } from "../i18n";

export const dashboardKey = ["dashboard"] as const;
export const meKey = ["me"] as const;

/** Full-width blue navigation: logo (home), destinations, streak, XP and the account menu. */
export function AppShell() {
  return (
    <div className="shell">
      <TopNav />
      <div className="content">
        <Outlet />
      </div>
    </div>
  );
}

export function TopNav() {
  const summary = useQuery({ queryKey: dashboardKey, queryFn: dashboard.get });
  const streak = summary.data?.streak.current;
  const xp = summary.data?.xp.total;
  const { t } = useI18n();
  return (
    <header className="topnav">
      <div className="topnav-inner">
        <Link to="/" className="home-link" aria-label={t("nav.home")}>
          <BrandLogo tone="white" height={26} />
        </Link>
        <nav className="nav-links" aria-label={t("nav.main")}>
          <NavLink to="/courses">{t("nav.courses")}</NavLink>
          <NavLink to="/review">{t("nav.review")}</NavLink>
          <NavLink to="/progress">{t("nav.progress")}</NavLink>
          <NavLink to="/community">{t("nav.community")}</NavLink>
          <NavLink to="/marketplace">{t("nav.marketplace")}</NavLink>
          <NavLink to="/guide">{t("nav.guide")}</NavLink>
        </nav>
        <div className="nav-stats">
          {streak !== undefined && (
            <span className="nav-stat" title={t("nav.streak", { n: streak })} aria-label={t("nav.streak", { n: streak })}>
              <FlameIcon /> {streak}
            </span>
          )}
          {xp !== undefined && (
            <span className="nav-stat xp-stat" title={t("nav.xp", { n: xp })} aria-label={t("nav.xp", { n: xp })}>
              <XpIcon /> {xp.toLocaleString()}
            </span>
          )}
          <AccountMenu />
        </div>
      </div>
    </header>
  );
}

function AccountMenu() {
  const { signOut } = useAuth();
  const { t } = useI18n();
  const me = useQuery({ queryKey: meKey, queryFn: auth.me });
  const [open, setOpen] = useState(false);
  const menuId = useId();
  const container = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent | KeyboardEvent) => {
      if (event instanceof KeyboardEvent ? event.key === "Escape" : !container.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);
  const name = me.data?.display_name || me.data?.email || "";
  return (
    <div className="account" ref={container}>
      <button
        type="button"
        className="account-button"
        aria-haspopup="true"
        aria-expanded={open}
        aria-controls={menuId}
        aria-label={t("account.menu")}
        onClick={() => setOpen((v) => !v)}
      >
        {name ? name[0]?.toUpperCase() : "·"}
      </button>
      {open && (
        <div className="account-menu" id={menuId}>
          {me.data?.display_name && <strong>{me.data.display_name}</strong>}
          <span className="email">{me.data?.email}</span>
          <Link to="/settings" className="button" onClick={() => setOpen(false)}>
            {t("account.settings")}
          </Link>
          <Link to="/guide" className="button" onClick={() => setOpen(false)}>
            {t("account.guide")}
          </Link>
          <button type="button" onClick={signOut}>
            {t("account.signOut")}
          </button>
        </div>
      )}
    </div>
  );
}

function zones(current: string): string[] {
  let all: string[] = [];
  try {
    all = Intl.supportedValuesOf("timeZone");
  } catch {
    // An older browser: only the current zone (and UTC) can be offered.
  }
  return Array.from(new Set([...all, "UTC", current].filter(Boolean)));
}

/** "UTC+02:00" for a zone right now ("" if the browser doesn't know the zone). */
function offsetLabel(zone: string): string {
  try {
    const part = new Intl.DateTimeFormat("en", { timeZone: zone, timeZoneName: "longOffset" })
      .formatToParts(new Date())
      .find((p) => p.type === "timeZoneName")?.value;
    return part === "GMT" ? "UTC+00:00" : (part ?? "").replace("GMT", "UTC");
  } catch {
    return "";
  }
}

/** Zones grouped by region ("Europe", "America", ...), each as "Rome (UTC+02:00)". */
function groupedZones(current: string): [string, { zone: string; label: string }[]][] {
  const groups = new Map<string, { zone: string; label: string }[]>();
  for (const zone of zones(current)) {
    const [region, ...rest] = zone.split("/");
    const city = (rest.join(" / ") || region || zone).replace(/_/g, " ");
    const offset = offsetLabel(zone);
    const key = rest.length ? (region ?? "Other") : "Other";
    groups.set(key, [...(groups.get(key) ?? []), { zone, label: offset ? `${city} (${offset})` : city }]);
  }
  return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
}

export function TimezoneForm({ current }: { current: string }) {
  const queryClient = useQueryClient();
  const { t } = useI18n();
  const [value, setValue] = useState(current);
  const groups = useMemo(() => groupedZones(current), [current]);
  const save = useMutation({
    mutationFn: (timezone: string) => auth.updateMe({ timezone }),
    onSuccess: (user) => {
      queryClient.setQueryData(meKey, user);
      void queryClient.invalidateQueries({ queryKey: dashboardKey });
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (value && value !== current) save.mutate(value);
  };
  return (
    <form onSubmit={submit} className="timezone-form">
      <label>
        {t("settings.timezone")}
        <select value={value} onChange={(e) => setValue(e.target.value)}>
          {groups.map(([region, list]) => (
            <optgroup key={region} label={region}>
              {list.map(({ zone, label }) => (
                <option key={zone} value={zone}>
                  {label}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
      </label>
      <ErrorBanner error={save.error} />
      <button type="submit" disabled={save.isPending || !value || value === current}>
        {t("common.save")}
      </button>
    </form>
  );
}

export function FlameIcon({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" focusable="false" className="flame">
      <path
        fill="currentColor"
        d="M12.6 2.2c.5 3.2-1.3 4.9-2.8 6.6C8.3 10.4 7 12 7 14.6 7 18.2 9.3 21 12.5 21c3.3 0 5.5-2.6 5.5-6 0-2.4-1.1-3.9-2.3-5.1-.2 1.6-.9 2.6-2 3.1.5-3.8-.3-7.2-1.1-10.8z"
      />
    </svg>
  );
}

/** XP: a four-point star, distinct from the streak flame. */
export function XpIcon({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" focusable="false" className="xp-symbol">
      <path fill="currentColor" d="M12 2l2.3 7.7L22 12l-7.7 2.3L12 22l-2.3-7.7L2 12l7.7-2.3z" />
    </svg>
  );
}
