import { expect, test } from "@playwright/test";

// The whole invitation journey in a real browser, against a backend with sign-up closed
// (REGISTRATION_OPEN=false) and one administrator. Not part of the default run: it needs its own
// stack (docs/MULTI_USER.md §5), pointed at by INVITE_E2E_URL, with INVITE_E2E_ADMIN_EMAIL and
// INVITE_E2E_ADMIN_PASSWORD for the administrator.
const URL = process.env.INVITE_E2E_URL;
test.skip(!URL, "set INVITE_E2E_URL to run the invitation journey");
test.use({ baseURL: URL });

const ADMIN_EMAIL = process.env.INVITE_E2E_ADMIN_EMAIL ?? "";
const ADMIN_PASSWORD = process.env.INVITE_E2E_ADMIN_PASSWORD ?? "";
const NEWCOMER = `newcomer-${Date.now()}@example.com`;
const PASSWORD = "a-long-enough-password-1";

test("an administrator invites someone, who receives the link and creates an account", async ({ page, browser }) => {
  test.setTimeout(240_000);

  // 1. The administrator signs in and creates an invitation.
  await page.goto("/");
  await page.getByLabel("Email or username").fill(ADMIN_EMAIL);
  await page.getByLabel("Password", { exact: true }).fill(ADMIN_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible();
  await page.getByRole("button", { name: "Account" }).click();
  await page.getByRole("link", { name: "Administration" }).click();
  await page.getByRole("button", { name: "Invitations" }).click();
  await page.getByLabel("Name or note").fill("Marco");
  await page.getByRole("button", { name: "Create invitation" }).click();
  const link = await page.getByLabel("Send this link to the person. It is shown only now:").inputValue();
  expect(link).toMatch(/\/\?invite=[\w-]{20,}$/);

  // 2. Without an invitation nobody can sign up.
  const stranger = await (await browser.newContext()).newPage();
  await stranger.goto("/");
  await stranger.getByRole("button", { name: "Create an account" }).click();
  await stranger.getByLabel("Email").fill(`stranger-${Date.now()}@example.com`);
  await stranger.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await stranger.getByRole("button", { name: "Create account" }).click();
  await expect(stranger.getByRole("alert")).toContainText("invitation");

  // 3. The invited person opens the link: the sign-up form is open with the code filled in.
  const guestContext = await browser.newContext();
  const guest = await guestContext.newPage();
  await guest.goto(link.replace(/^https?:\/\/[^/]+/, URL!));
  await expect(guest.getByLabel("Invitation code")).not.toHaveValue("");
  await guest.getByLabel("Email").fill(NEWCOMER);
  await guest.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await guest.getByRole("button", { name: "Create account" }).click();

  // 4. They are in: signed in, on their own empty dashboard.
  await expect(guest.getByRole("navigation", { name: "Main" })).toBeVisible();
  await guest.getByRole("button", { name: "Account" }).click();
  await expect(guest.getByText(NEWCOMER)).toBeVisible();
  await expect(guest.getByRole("link", { name: "Administration" })).toHaveCount(0); // not an administrator

  // 5. The same link doesn't work a second time.
  const reuse = await (await browser.newContext()).newPage();
  await reuse.goto(link.replace(/^https?:\/\/[^/]+/, URL!));
  await reuse.getByLabel("Email").fill(`second-${Date.now()}@example.com`);
  await reuse.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await reuse.getByRole("button", { name: "Create account" }).click();
  await expect(reuse.getByRole("alert")).toContainText("invitation");

  // 6. The administrator sees it used, and the new account listed (usage only, no content).
  await page.reload();
  await page.getByRole("button", { name: "Invitations" }).click();
  await expect(page.getByText(`Used by ${NEWCOMER}`)).toBeVisible();
  await page.getByRole("button", { name: "Accounts" }).click();
  await expect(page.getByText(NEWCOMER)).toBeVisible();

  // 7. The new person can sign out and back in with their email.
  // (the account menu is still open from step 4)
  await guest.getByRole("button", { name: "Sign out" }).click();
  await guest.getByLabel("Email or username").fill(NEWCOMER);
  await guest.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await guest.getByRole("button", { name: "Sign in" }).click();
  await expect(guest.getByRole("navigation", { name: "Main" })).toBeVisible();
});
