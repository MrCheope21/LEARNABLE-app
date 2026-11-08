import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";
import type { Schemas } from "../../api/client";
import { admin, auth } from "../../api/endpoints";
import { meKey } from "../../app/AppShell";
import { ErrorBanner, QueryState } from "../../components/QueryState";
import { dateTime } from "../../components/labels";
import { useI18n } from "../../i18n";
import type { MessageKey } from "../../i18n/messages/en";

type AdminUser = Schemas["AdminUser"];
type Invitation = Schemas["InvitationRead"];

const usersKey = ["admin", "users"] as const;
const invitationsKey = ["admin", "invitations"] as const;
const summaryKey = ["admin", "summary"] as const;

function megabytes(bytes: number): string {
  const mb = bytes / (1024 * 1024);
  return mb < 10 ? `${mb.toFixed(1)} MB` : `${Math.round(mb)} MB`;
}

/**
 * For the administrator only: invite people, see how much each account uses, suspend, set limits.
 * Never shows what anyone studies.
 */
export function AdminPage() {
  const { t } = useI18n();
  const me = useQuery({ queryKey: meKey, queryFn: auth.me });
  const [tab, setTab] = useState<"users" | "invites">("users");
  const summary = useQuery({ queryKey: summaryKey, queryFn: admin.summary, enabled: me.data?.is_admin === true });
  if (me.isPending) return <div className="state" role="status">{t("common.loading")}</div>;
  if (!me.data?.is_admin) return <Navigate to="/" replace />;
  return (
    <div className="page admin-page">
      <div className="page-header">
        <h1>{t("admin.title")}</h1>
        <p className="hint">{t("admin.intro")}</p>
        {summary.data && (
          <p className="hint">
            {t("admin.summary", { users: summary.data.users, ai: summary.data.ai_requests_today })}
            {summary.data.shared_daily_cap > 0 && ` · ${t("admin.sharedCap", { cap: summary.data.shared_daily_cap })}`}
          </p>
        )}
      </div>
      <nav className="tabs" aria-label={t("admin.title")}>
        <button type="button" aria-pressed={tab === "users"} onClick={() => setTab("users")}>
          {t("admin.tabUsers")}
        </button>
        <button type="button" aria-pressed={tab === "invites"} onClick={() => setTab("invites")}>
          {t("admin.tabInvites")}
        </button>
      </nav>
      {tab === "users" ? <Users myId={me.data.id} /> : <Invitations />}
    </div>
  );
}

function Users({ myId }: { myId: string }) {
  const users = useQuery({ queryKey: usersKey, queryFn: admin.users });
  return (
    <QueryState query={users}>
      {(rows) => (
        <ul className="admin-list">
          {rows.map((user) => (
            <li key={user.id}>
              <UserCard user={user} isMe={user.id === myId} />
            </li>
          ))}
        </ul>
      )}
    </QueryState>
  );
}

function UserCard({ user, isMe }: { user: AdminUser; isMe: boolean }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [shownPassword, setShownPassword] = useState<string | null>(null);
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: usersKey });
    void queryClient.invalidateQueries({ queryKey: summaryKey });
  };
  const toggle = useMutation({ mutationFn: () => admin.updateUser(user.id, { is_active: !user.is_active }), onSuccess: refresh });
  const reset = useMutation({
    mutationFn: () => admin.resetPassword(user.id),
    onSuccess: (result) => setShownPassword(result.password),
  });
  const remove = useMutation({ mutationFn: () => admin.deleteUser(user.id), onSuccess: refresh });
  const busy = toggle.isPending || reset.isPending || remove.isPending;

  return (
    <article className="card admin-user">
      <header className="card-header">
        <strong>
          {user.email}
          {user.username && <span className="hint"> @{user.username}</span>}
          {isMe && <span className="hint"> {t("admin.you")}</span>}
        </strong>
        <span>
          {user.is_admin && <span className="pill">{t("admin.isAdmin")}</span>}
          {!user.is_active && <span className="pill danger">{t("admin.isSuspended")}</span>}
          {user.custom_limits && <span className="pill">{t("admin.customLimits")}</span>}
        </span>
      </header>
      <p className="hint">
        {t("admin.joined", { date: dateTime(user.created_at) })} ·{" "}
        {user.last_active_at ? t("admin.lastActive", { date: dateTime(user.last_active_at) }) : t("admin.neverActive")}
      </p>
      <p>{t("admin.usage", { courses: user.course_count, answers: user.answer_count, storage: megabytes(user.storage_bytes) })}</p>
      <p className="hint">
        {t("admin.today", {
          ev: user.evaluations_today,
          evLimit: user.evaluations_limit,
          gen: user.generations_today,
          genLimit: user.generations_limit,
        })}
      </p>
      {shownPassword && (
        <p className="banner info" role="status">
          {t("admin.passwordShown", { email: user.email, password: shownPassword })}
        </p>
      )}
      {!isMe && (
        <div className="actions">
          <button type="button" disabled={busy} onClick={() => toggle.mutate()}>
            {user.is_active ? t("admin.suspend") : t("admin.reactivate")}
          </button>
          <button type="button" disabled={busy} onClick={() => setEditing((v) => !v)}>
            {t("admin.limits")}
          </button>
          <button type="button" disabled={busy} onClick={() => reset.mutate()}>
            {t("admin.newPassword")}
          </button>
          <button
            type="button"
            className="link danger"
            disabled={busy}
            onClick={() => {
              if (window.confirm(t("admin.deleteConfirm", { email: user.email }))) remove.mutate();
            }}
          >
            {t("admin.delete")}
          </button>
        </div>
      )}
      {editing && <LimitsForm user={user} onDone={() => { setEditing(false); refresh(); }} />}
      <ErrorBanner error={toggle.error ?? reset.error ?? remove.error} />
    </article>
  );
}

function LimitsForm({ user, onDone }: { user: AdminUser; onDone: () => void }) {
  const { t } = useI18n();
  const ids = useId();
  const [evaluations, setEvaluations] = useState(String(user.evaluations_limit));
  const [generations, setGenerations] = useState(String(user.generations_limit));
  const [storage, setStorage] = useState(String(Math.round(user.storage_limit_bytes / (1024 * 1024))));
  const save = useMutation({
    mutationFn: (body: Schemas["AdminUserUpdate"]) => admin.updateUser(user.id, body),
    onSuccess: onDone,
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate({
      limit_evaluations: Number(evaluations),
      limit_generations: Number(generations),
      limit_storage_mb: Number(storage),
    });
  };
  return (
    <form className="settings-form admin-limits" onSubmit={submit}>
      <label htmlFor={`${ids}-e`}>{t("admin.limitEval")}</label>
      <input id={`${ids}-e`} type="number" min={0} value={evaluations} onChange={(e) => setEvaluations(e.target.value)} />
      <label htmlFor={`${ids}-g`}>{t("admin.limitGen")}</label>
      <input id={`${ids}-g`} type="number" min={0} value={generations} onChange={(e) => setGenerations(e.target.value)} />
      <label htmlFor={`${ids}-s`}>{t("admin.limitStorage")}</label>
      <input id={`${ids}-s`} type="number" min={0} value={storage} onChange={(e) => setStorage(e.target.value)} />
      <div className="actions">
        <button type="submit" className="primary" disabled={save.isPending}>
          {t("common.save")}
        </button>
        <button
          type="button"
          disabled={save.isPending}
          onClick={() => save.mutate({ limit_evaluations: null, limit_generations: null, limit_storage_mb: null })}
        >
          {t("admin.useDefaults")}
        </button>
      </div>
      <ErrorBanner error={save.error} />
    </form>
  );
}

function Invitations() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const ids = useId();
  const [note, setNote] = useState("");
  const [email, setEmail] = useState("");
  const [days, setDays] = useState("7");
  const [sendEmail, setSendEmail] = useState(true);
  const summary = useQuery({ queryKey: summaryKey, queryFn: admin.summary });
  const canEmail = summary.data?.email_enabled === true;
  const [created, setCreated] = useState<Schemas["InvitationCreated"] | null>(null);
  const [copied, setCopied] = useState(false);
  const list = useQuery({ queryKey: invitationsKey, queryFn: admin.invitations });
  const create = useMutation({
    mutationFn: () => admin.createInvitation({ note: note.trim(), email: email.trim() || null, days: Number(days) || null, send_email: sendEmail }),
    onSuccess: (invitation) => {
      setCreated(invitation);
      setCopied(false);
      setNote("");
      setEmail("");
      void queryClient.invalidateQueries({ queryKey: invitationsKey });
    },
  });
  const revoke = useMutation({
    mutationFn: (id: string) => admin.revokeInvitation(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: invitationsKey }),
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    create.mutate();
  };
  const copy = async (link: string) => {
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
    } catch {
      // The link stays selectable on screen.
    }
  };
  return (
    <>
      <form className="card settings-form" onSubmit={submit}>
        <label htmlFor={`${ids}-n`}>{t("admin.invNote")}</label>
        <input id={`${ids}-n`} value={note} maxLength={120} onChange={(e) => setNote(e.target.value)} />
        <label htmlFor={`${ids}-m`}>{t("admin.invEmail")}</label>
        <input id={`${ids}-m`} type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        {canEmail && email.trim() && (
          <label className="toggle">
            <input type="checkbox" checked={sendEmail} onChange={(e) => setSendEmail(e.target.checked)} />
            {t("admin.invSend")}
          </label>
        )}
        <label htmlFor={`${ids}-d`}>{t("admin.invDays")}</label>
        <input id={`${ids}-d`} type="number" min={1} max={90} value={days} onChange={(e) => setDays(e.target.value)} />
        <div className="actions">
          <button type="submit" className="primary" disabled={create.isPending}>
            {t("admin.invCreate")}
          </button>
        </div>
        <ErrorBanner error={create.error} />
      </form>
      {created && (
        <section className="card" role="status">
          {created.emailed && created.email && <p className="banner info">{t("admin.invEmailed", { email: created.email })}</p>}
          <p>{t("admin.invLink")}</p>
          <p>
            <input readOnly value={created.link} aria-label={t("admin.invLink")} onFocus={(e) => e.currentTarget.select()} style={{ width: "100%" }} />
          </p>
          <button type="button" onClick={() => void copy(created.link)}>
            {copied ? t("admin.copied") : t("admin.copy")}
          </button>
        </section>
      )}
      <QueryState query={list}>
        {(rows) =>
          rows.length === 0 ? (
            <p className="state">{t("admin.invNone")}</p>
          ) : (
            <ul className="admin-list">
              {rows.map((invitation) => (
                <li key={invitation.id}>
                  <InvitationRow invitation={invitation} onRevoke={() => revoke.mutate(invitation.id)} busy={revoke.isPending} />
                </li>
              ))}
            </ul>
          )
        }
      </QueryState>
      <ErrorBanner error={revoke.error} />
    </>
  );
}

function InvitationRow({ invitation, onRevoke, busy }: { invitation: Invitation; onRevoke: () => void; busy: boolean }) {
  const { t } = useI18n();
  return (
    <article className="card admin-invitation">
      <header className="card-header">
        <strong>{invitation.note || invitation.email || "—"}</strong>
        <span className="pill">{t(`admin.invStatus.${invitation.status}` as MessageKey)}</span>
      </header>
      <p className="hint">
        {invitation.email && `${invitation.email} · `}
        {invitation.status === "used" && invitation.used_by_email
          ? t("admin.invUsedBy", { email: invitation.used_by_email })
          : t("admin.invExpires", { date: dateTime(invitation.expires_at) })}
      </p>
      {invitation.status === "pending" && (
        <div className="actions">
          <button type="button" className="link danger" disabled={busy} onClick={onRevoke}>
            {t("admin.revoke")}
          </button>
        </div>
      )}
    </article>
  );
}
