import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { tokenStore } from "../../api/client";
import { en } from "../../i18n/messages/en";
import { mockApi, ok } from "../../test/mockApi";
import { renderApp } from "../../test/render";

const me = { id: "u1", email: "ada@example.com", timezone: "Europe/Rome", daily_goal: 20, language: "en", display_name: null };

function backend(user = me) {
  return mockApi([
    ["GET", /\/auth\/me$/, ok(user)],
    ["PATCH", /\/auth\/me$/, (request) => ({ body: { ...user, ...(request.body as object) } })],
    ["GET", /\/dashboard$/, () => ({ status: 503, body: { error_type: "internal_error", message: "x", details: {} } })],
  ]);
}

afterEach(() => {
  document.documentElement.lang = "";
  document.documentElement.dir = "";
});

describe("settings", () => {
  it("switches the whole interface language and saves it to the account", async () => {
    const user = userEvent.setup();
    const { requests } = backend();
    renderApp("/settings");

    await user.click(await screen.findByRole("radio", { name: "Italiano" }));
    expect(await screen.findByRole("heading", { name: "Impostazioni" })).toBeInTheDocument();
    expect(within(screen.getByRole("navigation", { name: "Principale" })).getByRole("link", { name: "Corsi" })).toBeInTheDocument();
    expect(document.documentElement.lang).toBe("it");
    await waitFor(() => expect(requests.find((r) => r.method === "PATCH")?.body).toEqual({ language: "it" }));
  });

  it("lays Arabic out right to left", async () => {
    const user = userEvent.setup();
    backend();
    renderApp("/settings");
    await user.click(await screen.findByRole("radio", { name: "العربية" }));
    await waitFor(() => expect(document.documentElement.dir).toBe("rtl"));
    await user.click(screen.getByRole("radio", { name: "English" }));
    await waitFor(() => expect(document.documentElement.dir).toBe("ltr"));
  });

  it("follows the language saved on the account", async () => {
    backend({ ...me, language: "de" });
    renderApp("/settings");
    expect(await screen.findByRole("heading", { name: "Einstellungen" })).toBeInTheDocument();
  });

  it("saves a display name and shows it instead of the email", async () => {
    const user = userEvent.setup();
    const { requests } = backend();
    renderApp("/settings");
    await user.type(await screen.findByLabelText("Display name"), "Ada");
    await user.click(within(screen.getByRole("region", { name: "Profile" })).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(requests.find((r) => r.method === "PATCH")?.body).toEqual({ display_name: "Ada" }));
    expect(await screen.findByText("Saved.")).toBeInTheDocument();
  });

  it("changes the daily goal within its limits", async () => {
    const user = userEvent.setup();
    const { requests } = backend();
    renderApp("/settings");
    const goal = await screen.findByLabelText("Daily goal");
    const save = within(goal.closest("form")!).getByRole("button", { name: "Save" });
    await user.clear(goal);
    await user.type(goal, "0");
    expect(save).toBeDisabled();
    await user.clear(goal);
    await user.type(goal, "35");
    await user.click(save);
    await waitFor(() => expect(requests.find((r) => r.method === "PATCH")?.body).toEqual({ daily_goal: 35 }));
  });
});

describe("guide", () => {
  it("explains every step and the glossary, in the chosen language", async () => {
    backend({ ...me, language: "es" });
    renderApp("/guide");
    expect(await screen.findByRole("heading", { level: 1, name: "Cómo funciona LEARNABLE" })).toBeInTheDocument();
    expect(screen.getAllByRole("region")).toHaveLength(12);
    expect(screen.getByRole("link", { name: "Repasa a tiempo" })).toHaveAttribute("href", "#guide-review");
  });
});

describe("sign-in page", () => {
  it("can be switched to another language before signing in, and registration keeps it", async () => {
    tokenStore.clear();
    const user = userEvent.setup();
    const { requests } = mockApi([["POST", /\/auth\/register$/, ok({ ...me, language: "fr" })], ["POST", /\/auth\/login$/, ok({ access_token: "t", token_type: "bearer" })]]);
    renderApp("/", { signedIn: false });
    await user.selectOptions(screen.getByLabelText(en["signin.language"]), "fr");
    expect(screen.getByRole("heading", { name: "Connexion à LEARNABLE" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Créer un compte" }));
    await user.type(screen.getByLabelText("E-mail"), "new@example.com");
    await user.type(screen.getByLabelText("Mot de passe"), "a-long-enough-password");
    await user.click(screen.getByRole("button", { name: "Créer le compte" }));
    await waitFor(() => expect(requests.find((r) => r.path.endsWith("/register"))?.body).toMatchObject({ language: "fr" }));
  });
});
