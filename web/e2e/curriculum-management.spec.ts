import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// Reordering (components/SortableList.tsx) and collapsing (components/Collapsible.tsx) in a real
// browser. Self-contained: each test registers its own user and builds its own course through the
// API, so it needs no seed data.
const PASSWORD = "curriculum-e2e-password";

type Course = { id: string; chapters: string[]; concept: string; items: string[] };

async function created(request: APIRequestContext, path: string, token: string, data: object): Promise<string> {
  const response = await request.post(`/api/v1${path}`, { data, headers: { Authorization: `Bearer ${token}` } });
  expect(response.status(), path).toBe(201);
  return ((await response.json()) as { id: string }).id;
}

async function setUp(request: APIRequestContext, email: string): Promise<{ token: string; course: Course }> {
  expect((await request.post("/api/v1/auth/register", { data: { email, password: PASSWORD } })).status()).toBe(201);
  const login = await request.post("/api/v1/auth/login", { data: { email, password: PASSWORD } });
  const token = ((await login.json()) as { access_token: string }).access_token;
  const id = await created(request, "/courses", token, { title: "Reorder course" });
  const chapters: string[] = [];
  for (const [order, title] of ["Alpha", "Beta", "Gamma"].entries()) {
    chapters.push(await created(request, `/courses/${id}/chapters`, token, { title, order }));
  }
  const topic = await created(request, `/chapters/${chapters[0]}/topics`, token, { title: "Topic" });
  const concept = await created(request, `/topics/${topic}/concepts`, token, { title: "Concept" });
  const items: string[] = [];
  for (const text of ["First question?", "Second question?", "Third question?"]) {
    items.push(
      await created(request, `/concepts/${concept}/learning-items`, token, {
        title: text,
        questions: [{ question_type: "RECALL", text }],
      }),
    );
  }
  return { token, course: { id, chapters, concept, items } };
}

async function signIn(page: Page, email: string) {
  await page.goto("/");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible();
}

function saved(page: Page, path: RegExp) {
  return page.waitForResponse((r) => r.request().method() === "PUT" && path.test(new URL(r.url()).pathname));
}

test("chapters move with the keyboard, questions with the mouse, and the order is saved", async ({ page, request }) => {
  const email = `reorder-${Date.now()}@example.com`;
  const { token, course } = await setUp(request, email);
  const auth = { headers: { Authorization: `Bearer ${token}` } };
  await signIn(page, email);

  // Chapters, keyboard only: focus the handle, Space to pick up, ArrowDown, Space to drop.
  await page.goto(`/courses/${course.id}`);
  const chapterRows = page.locator(".sortable-row");
  await expect(chapterRows).toHaveText([/Alpha/, /Beta/, /Gamma/]);
  await page.getByRole("button", { name: "Reorder Alpha" }).focus();
  const chapterSave = saved(page, /\/chapter-order$/);
  // Each step waits for its screen-reader announcement, as the list measures itself on pickup.
  await page.keyboard.press("Space");
  await expect(page.getByRole("status").filter({ hasText: /Alpha.*position 1 of 3/ })).toBeAttached();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByRole("status").filter({ hasText: "Alpha is now at position 2 of 3" })).toBeAttached();
  await page.keyboard.press("Space");
  expect((await chapterSave).status()).toBe(204);
  await expect(chapterRows).toHaveText([/Beta/, /Alpha/, /Gamma/]);
  const outline = (await (await request.get(`/api/v1/courses/${course.id}/outline`, auth)).json()) as { title: string }[];
  expect(outline.map((c) => c.title)).toEqual(["Beta", "Alpha", "Gamma"]);

  // Questions, by mouse: drag the first below the third.
  await page.goto(`/courses/${course.id}/questions`);
  const questionRows = page.locator(".question-list .sortable-row");
  await expect(questionRows).toHaveText([/First/, /Second/, /Third/]);
  const handle = page.getByRole("button", { name: "Reorder First question?" });
  const target = (await questionRows.nth(2).boundingBox())!;
  const from = (await handle.boundingBox())!;
  const itemSave = saved(page, /\/learning-item-order$/);
  await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2);
  await page.mouse.down();
  await page.mouse.move(from.x + from.width / 2, from.y + 20, { steps: 5 });
  await page.mouse.move(from.x + from.width / 2, target.y + target.height - 4, { steps: 15 });
  await page.mouse.up();
  expect((await itemSave).status()).toBe(204);
  await expect(questionRows).toHaveText([/Second/, /Third/, /First/]);
  const listed = (await (await request.get(`/api/v1/concepts/${course.concept}/learning-items`, auth)).json()) as { title: string }[];
  expect(listed.map((i) => i.title)).toEqual(["Second question?", "Third question?", "First question?"]);

  // While a search hides part of the list, there's nothing to drag.
  await page.getByLabel("Search questions").fill("question");
  await expect(page.getByRole("button", { name: /^Reorder / })).toHaveCount(0);
  await expect(page.getByText("Clear the search to reorder these questions.")).toBeVisible();
});

test("chapters, topics and concepts collapse one by one, and stay collapsed after a reload", async ({ page, request }) => {
  const email = `collapse-${Date.now()}@example.com`;
  const { course } = await setUp(request, email);
  await signIn(page, email);

  // The question manager: collapse a single chapter.
  await page.goto(`/courses/${course.id}/questions`);
  const main = page.locator(".workspace-main");
  const firstQuestion = main.getByText("First question?");
  await expect(firstQuestion).toBeVisible();
  await main.getByRole("button", { name: "Collapse Alpha" }).click();
  await expect(firstQuestion).toBeHidden();
  await expect(main.getByRole("button", { name: "Expand Alpha" })).toHaveAttribute("aria-expanded", "false");
  await page.reload();
  await expect(main.getByRole("button", { name: "Expand Alpha" })).toBeVisible();
  await expect(firstQuestion).toBeHidden();
  // A search never hides its results inside a collapsed section.
  await page.getByLabel("Search questions").fill("First");
  await expect(firstQuestion).toBeVisible();
  await page.getByLabel("Search questions").fill("");
  await expect(firstQuestion).toBeHidden();
  await main.getByRole("button", { name: "Expand all" }).click();
  await expect(firstQuestion).toBeVisible();
  // A single concept collapses on its own and says how much it holds.
  await main.getByRole("button", { name: "Collapse Concept" }).click();
  await expect(firstQuestion).toBeHidden();
  await expect(main.getByText("3 questions")).toBeVisible();

  // The course tree: collapsing a chapter hides its topics...
  const tree = page.getByRole("navigation", { name: "Curriculum" });
  await tree.getByRole("button", { name: "Collapse Alpha" }).click();
  await expect(tree.getByRole("link", { name: "Topic" })).toBeHidden();
  // ...but the branch of the page you open stays visible.
  await page.goto(`/courses/${course.id}/concepts/${course.concept}`);
  await expect(tree.getByRole("link", { name: "Concept" })).toBeVisible();
});
