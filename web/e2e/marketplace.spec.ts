import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// The marketplace end to end: an author writes the course's marketplace page and publishes it;
// another user finds it by category, sees only its presentation and size, adds it, and gets a
// read-only course on their dashboard. Self-contained (own users).
const PASSWORD = "marketplace-e2e-password";

async function signUp(request: APIRequestContext, email: string) {
  expect((await request.post("/api/v1/auth/register", { data: { email, password: PASSWORD } })).status()).toBe(201);
  const login = await request.post("/api/v1/auth/login", { data: { email, password: PASSWORD } });
  return { Authorization: `Bearer ${((await login.json()) as { access_token: string }).access_token}` };
}

async function signIn(page: Page, email: string) {
  await page.goto("/");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible();
}

test("an author publishes a course and another user adds it to their courses", async ({ browser, request }) => {
  const stamp = Date.now();
  const author = `author-${stamp}@example.com`;
  const buyer = `buyer-${stamp}@example.com`;
  const headers = await signUp(request, author);
  await signUp(request, buyer);
  await request.patch("/api/v1/auth/me", { data: { display_name: "Prof. Rossi" }, headers });
  const post = async (path: string, data: object) => ((await (await request.post(`/api/v1${path}`, { data, headers })).json()) as { id: string }).id;
  const title = `Imprenditore ${stamp}`;
  const course = await post("/courses", { title, language: "it" });
  const chapter = await post(`/courses/${course}/chapters`, { title: "L'imprenditore" });
  const topic = await post(`/chapters/${chapter}/topics`, { title: "Nozione" });
  const concept = await post(`/topics/${topic}/concepts`, { title: "Art. 2082 c.c." });
  await post(`/concepts/${concept}/learning-items`, {
    title: "Chi è imprenditore",
    expected_knowledge: "Chi esercita professionalmente un'attività economica organizzata.",
    questions: [{ question_type: "DEFINITION", text: "Chi è imprenditore ai sensi dell'art. 2082 c.c.?" }],
  });

  // The author writes the marketplace page on the course and publishes it.
  const authorPage = await (await browser.newContext()).newPage();
  await signIn(authorPage, author);
  await authorPage.goto(`/courses/${course}`);
  await authorPage.getByRole("button", { name: "Write a marketplace page" }).click();
  await authorPage.getByLabel("Subtitle").fill("Tutte le domande dell'orale");
  await authorPage.getByLabel("Category").selectOption("law");
  await authorPage.getByLabel("Description").fill("Le domande sull'imprenditore, con risposte modello.");
  await authorPage.getByLabel("What students will learn").fill("Definire l'imprenditore");
  await authorPage.getByRole("button", { name: "Save draft" }).click();
  await expect(authorPage.getByText("Draft saved.", { exact: false })).toBeVisible();
  await authorPage.getByLabel(/are mine to share/).check();
  await authorPage.getByRole("button", { name: "Publish", exact: true }).click();
  await expect(authorPage.getByText("Published!", { exact: false })).toBeVisible();

  // The buyer finds it under Law and sees its page, without its questions.
  const page = await (await browser.newContext()).newPage();
  await signIn(page, buyer);
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Marketplace" }).click();
  await page.getByRole("button", { name: /Law/ }).click();
  await page.getByRole("link", { name: title }).click();
  await expect(page.getByRole("heading", { name: title })).toBeVisible();
  await expect(page.getByText("Definire l'imprenditore")).toBeVisible();
  await expect(page.getByText("1 questions")).toBeVisible();
  await expect(page.getByText("Chi è imprenditore ai sensi")).toHaveCount(0);

  await page.getByRole("button", { name: /Add to my courses/ }).click();
  await expect(page.getByRole("heading", { name: "🛒 From the marketplace" })).toBeVisible();
  await expect(page.getByText("Prof. Rossi").first()).toBeVisible();
  await expect(page.getByRole("button", { name: /^Rename/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Add chapter" })).toHaveCount(0);

  await page.goto("/");
  await expect(page.getByText("From the marketplace · by Prof. Rossi")).toBeVisible();
  // Nothing in the page overflows sideways (the new badges and filters included).
  await page.goto("/marketplace");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});
