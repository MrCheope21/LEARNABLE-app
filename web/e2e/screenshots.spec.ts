import { expect, test, type Page } from "@playwright/test";

// Captures the documentation screenshots in docs/screenshots (not part of the CI run):
//   CAPTURE_SCREENSHOTS=1 npx playwright test screenshots
// Needs the demo backend (scripts/seed_demo.py); run after vertical-slice so there is history.
test.skip(!process.env.CAPTURE_SCREENSHOTS, "set CAPTURE_SCREENSHOTS=1 to capture");

const OUT = "../docs/screenshots";
const WIDTHS = [1440, 1024, 768, 390];

async function signIn(page: Page) {
  await page.goto("/");
  await page.getByLabel("Email").fill("demo@example.com");
  await page.getByLabel("Password").fill("learnable-demo-2026");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible();
}

test("dashboard at four widths", async ({ page }) => {
  await signIn(page);
  const token = await page.evaluate(() => localStorage.getItem("learnable.accessToken"));
  const headers = { Authorization: `Bearer ${token}` };
  const existing = (await (await page.request.get("/api/v1/courses", { headers })).json()) as { title: string }[];
  for (const [title, description] of [
    ["Diritto tributario: IRES e reddito d'impresa per il bilancio d'esercizio", "Imposta sul reddito delle società, dal risultato civilistico al reddito imponibile"],
    ["Microeconomia", "Domanda, offerta, equilibrio"],
  ]) {
    if (!existing.some((c) => c.title === title)) {
      await page.request.post("/api/v1/courses", { headers, data: { title, description, language: "it" } });
    }
  }
  for (const width of WIDTHS) {
    await page.setViewportSize({ width, height: width < 500 ? 844 : 900 });
    await page.goto("/");
    await expect(page.getByRole("region", { name: "Daily streak" })).toBeVisible();
    await page.screenshot({ path: `${OUT}/dashboard-${width}.png`, fullPage: true });
    // No horizontal page scroll at any width.
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, `horizontal overflow at ${width}px`).toBeLessThanOrEqual(0);
  }
});

test("study before and after a hint", async ({ page }) => {
  await signIn(page);
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.getByRole("link", { name: "Diritto bancario (demo)", exact: true }).first().click();
  const tree = page.getByRole("navigation", { name: "Curriculum" });
  await tree.locator("a.tree-concept").nth(1).click();
  await expect(page.locator(".page-header .pill")).toBeVisible();
  const activate = page.getByRole("button", { name: "Activate" });
  if (await activate.isVisible()) await activate.click();
  await page.getByRole("button", { name: /I have studied this concept|Resume/ }).click({ timeout: 30_000 });
  await expect(page.getByText(/Round \d of 3/)).toBeVisible();
  await page.screenshot({ path: `${OUT}/study-before-hint.png` });
  await page.getByRole("button", { name: "Show hint" }).click();
  await page.getByRole("button", { name: "Reveal hint" }).click();
  await expect(page.getByText(/half XP/)).toBeVisible();
  await page.getByLabel("Your answer").fill("Il contratto con cui la banca tiene a disposizione del cliente una somma di denaro.");
  await page.screenshot({ path: `${OUT}/study-after-hint.png` });
  await page.getByLabel("Your answer").press("Control+Enter");
  await expect(page.locator(".award")).toBeVisible({ timeout: 30_000 });
  await page.screenshot({ path: `${OUT}/study-result.png`, fullPage: true });
});

test("brand concepts", async ({ page }) => {
  await page.setViewportSize({ width: 900, height: 420 });
  await page.goto("/");
  await page.setContent(`
    <body style="margin:0;font-family:system-ui">
      <div style="padding:28px;display:flex;gap:40px;align-items:center;background:#fff">
        <img src="http://localhost:5173/brand/concept5-wordmark-blue.svg" height="44">
        <img src="http://localhost:5173/brand/concept5-app-icon.svg" height="64">
        <img src="http://localhost:5173/brand/concept5-app-icon.svg" height="16">
        <img src="http://localhost:5173/brand/concept5-wordmark-mono.svg" height="22">
      </div>
      <div style="padding:18px 28px;background:#1555DD"><img src="http://localhost:5173/brand/concept5-wordmark-white.svg" height="28"></div>
      <div style="padding:28px;display:flex;gap:40px;align-items:center;background:#fff">
        <img src="http://localhost:5173/brand/concept3-wordmark-blue.svg" height="44">
        <img src="http://localhost:5173/brand/concept3-app-icon.svg" height="64">
        <img src="http://localhost:5173/brand/concept3-app-icon.svg" height="16">
      </div>
      <div style="padding:18px 28px;background:#1555DD"><img src="http://localhost:5173/brand/concept3-wordmark-white.svg" height="28"></div>
    </body>`);
  await page.waitForLoadState("networkidle");
  await page.screenshot({ path: `${OUT}/brand-concepts.png` });
});
