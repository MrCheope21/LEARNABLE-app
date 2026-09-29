import { expect, test, type Page } from "@playwright/test";

// Seeded by backend/scripts/seed_demo.py (AI_PROVIDER=mock) on a fresh database.
const EMAIL = "demo@example.com";
const PASSWORD = "learnable-demo-2026";
const COURSE = "Diritto bancario (demo)";
// Close to the seeded material, so the mock evaluator (keyword overlap) grades it correct.
const ANSWER =
  "Il deposito bancario e il contratto con cui la banca acquista la proprieta del denaro depositato. " +
  "Il depositante ha diritto alla restituzione della somma alla scadenza o a richiesta.";

type Schedule = { next_level: number; next_due_at: string | null };
type Xp = { correct: boolean; xp: number; hint_used: boolean; ordinal: number | null };
type AnswerResult = {
  answer_id: string;
  learning_item_id: string;
  final_outcome: string;
  schedule: Schedule | null;
  consolidation_round: number | null;
  xp: Xp | null;
};
type ReviewRow = {
  id: string;
  answer_id: string;
  intent: string;
  outcome: string;
  previous_level: number;
  next_level: number;
  next_due_at: string | null;
  reviewed_at: string;
  supersedes_review_id: string | null;
  superseded: boolean;
};
type Dashboard = { xp: { total: number; today: number }; streak: { current: number }; goal: { done: number } };

function responseTo(page: Page, method: string, path: RegExp) {
  return page.waitForResponse((r) => r.request().method() === method && path.test(new URL(r.url()).pathname));
}

async function token(page: Page): Promise<string | null> {
  return page.evaluate(() => localStorage.getItem("learnable.accessToken"));
}

/** The API as the signed-in browser session sees it (same token, same proxy). */
async function apiGet<T>(page: Page, path: string, expected = 200): Promise<T> {
  const response = await page.request.get(path, { headers: { Authorization: `Bearer ${await token(page)}` } });
  expect(response.status(), path).toBe(expected);
  return (await response.json()) as T;
}

async function signIn(page: Page, email = EMAIL, password = PASSWORD) {
  await page.goto("/");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible();
}

async function answerCurrent(page: Page): Promise<AnswerResult> {
  await page.getByLabel("Your answer").fill(ANSWER);
  const answered = responseTo(page, "POST", /^\/api\/v1\/review-sessions\/[^/]+\/answers$/);
  await page.getByLabel("Your answer").press("Control+Enter");
  const result = (await (await answered).json()) as AnswerResult;
  await expect(page.locator(".outcome-badge")).toBeVisible({ timeout: 30_000 });
  return result;
}

test("consolidation loop: concept → activate → I have studied it → 3 rounds with a hint → XP → dashboard", async ({ page }) => {
  const startedAt = Date.now();
  await signIn(page);

  // Dashboard → course card → course workspace with the curriculum tree.
  await page.getByRole("link", { name: COURSE, exact: true }).first().click();
  const tree = page.getByRole("navigation", { name: "Curriculum" });
  await expect(tree.getByRole("link", { name: "Contratti bancari" })).toBeVisible();
  await tree.getByRole("link", { name: "Contratti bancari" }).click();
  await expect(page.getByRole("heading", { name: "Topics" })).toBeVisible();
  await tree.locator("a.tree-topic").first().click();
  await expect(page.getByRole("heading", { name: "Concepts" })).toBeVisible();
  await tree.locator("a.tree-concept").first().click();

  // Activating prepares questions, but isn't studying: that's the user's explicit statement.
  await page.getByRole("button", { name: "Activate" }).click();
  const studied = page.getByRole("button", { name: "I have studied this concept" });
  await expect(studied).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/answers/).filter({ hasText: "This batch" })).toBeVisible();
  await studied.click();

  // Round 1 of 3, with the potential XP; a hint is confirmed before it is shown.
  await expect(page.getByText("Round 1 of 3")).toBeVisible();
  await expect(page.getByText(/Correct answer: \+10 XP/)).toBeVisible();
  await page.getByRole("button", { name: "Show hint" }).click();
  await expect(page.getByText("Using a hint halves the XP for this answer.")).toBeVisible();
  await page.getByRole("button", { name: "Reveal hint" }).click();
  await expect(page.getByText(/Correct answer: \+5 XP/)).toBeVisible();
  // The reveal is stored on the server: a reload keeps it.
  await page.reload();
  await expect(page.getByText(/Correct answer: \+5 XP/)).toBeVisible();

  const first = await answerCurrent(page);
  expect(first.consolidation_round).toBe(1);
  expect(first.xp).toMatchObject({ correct: true, xp: 5, hint_used: true, ordinal: 1 });
  await expect(page.getByText(/Correct · \+5 XP · Hint used/)).toBeVisible();
  expect(first.schedule).toBeNull(); // rounds seconds apart aren't reviews

  // Rounds 2 and 3 of the same item: 20 and 30 XP.
  await page.getByRole("button", { name: /Continue/ }).click();
  await expect(page.getByText("Round 2 of 3")).toBeVisible();
  const second = await answerCurrent(page);
  expect(second.xp?.xp).toBe(20);
  await page.getByRole("button", { name: /Continue/ }).click();
  await expect(page.getByText("Round 3 of 3")).toBeVisible();
  const third = await answerCurrent(page);
  expect(third.xp?.xp).toBe(30);
  // Only the last round is scheduled: an encoding, level 0 → 1.
  expect(third.schedule?.next_level).toBe(1);

  // Disagree on round 3 → Hard: the schedule is replayed, the XP stays as decided.
  await page.getByRole("button", { name: "Disagree with the grade?" }).click();
  const overridden = responseTo(page, "POST", new RegExp(`^/api/v1/answers/${third.answer_id}/override$`));
  await page.getByRole("button", { name: /^Hard/ }).click();
  const override = (await (await overridden).json()) as AnswerResult;
  expect(override.final_outcome).toBe("HARD");
  expect(override.xp?.xp).toBe(30);
  await expect(page.getByText("Graded by you")).toBeVisible();

  // Finish the batch (other items, if the concept has several).
  for (let i = 0; i < 20; i++) {
    if (await page.getByText("Batch consolidated").isVisible()) break;
    const cont = page.getByRole("button", { name: /Continue/ });
    if (await cont.isVisible()) await cont.click();
    else if (await page.getByLabel("Your answer").isVisible()) await answerCurrent(page);
    await page.waitForTimeout(200);
  }
  await expect(page.getByText("Batch consolidated")).toBeVisible();
  await page.getByRole("button", { name: "Done" }).click();

  // The logo goes to the dashboard, which reflects the study immediately.
  await page.getByRole("link", { name: "LEARNABLE home" }).click();
  await expect(page.getByRole("region", { name: "Experience" })).toContainText("XP today");
  const dashboard = await apiGet<Dashboard>(page, "/api/v1/dashboard");
  expect(dashboard.xp.today).toBeGreaterThanOrEqual(55);
  expect(dashboard.streak.current).toBeGreaterThanOrEqual(1);
  expect(dashboard.goal.done).toBeGreaterThanOrEqual(3);
  await expect(page.getByLabel(`Total experience: ${dashboard.xp.total} XP`)).toBeVisible();

  await page.getByRole("link", { name: "Progress" }).click();
  await expect(page.getByRole("heading", { name: "Curriculum", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Memory", exact: true })).toBeVisible();

  // The stored history of round 3: the AI-graded review kept, superseded by the user's grade.
  const history = await apiGet<ReviewRow[]>(page, `/api/v1/learning-items/${third.learning_item_id}/reviews`);
  const rows = history.filter((r) => r.answer_id === third.answer_id);
  expect(rows).toHaveLength(2);
  const aiGraded = rows.find((r) => r.superseded);
  const userGraded = rows.find((r) => !r.superseded);
  expect(aiGraded?.outcome).toBe(third.final_outcome);
  expect(userGraded?.supersedes_review_id).toBe(aiGraded?.id);
  expect(userGraded?.intent).toBe("CONSOLIDATION");
  expect(userGraded?.outcome).toBe("HARD");
  expect(Date.parse(userGraded!.reviewed_at)).toBeGreaterThanOrEqual(startedAt - 60_000);
  expect(history.filter((r) => r.answer_id === first.answer_id)).toHaveLength(0);
});

test("two accounts: private material, private metrics, nothing cached across sign-in", async ({ page }) => {
  // B registers through the app.
  const email = `learner-${Date.now()}@example.com`;
  const password = "another-learner-password";
  await page.goto("/");
  await page.getByRole("button", { name: "Create an account" }).click();
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByText("Start your first course")).toBeVisible();
  await expect(page.getByText(COURSE)).toHaveCount(0);
  const theirs = await apiGet<Dashboard>(page, "/api/v1/dashboard");
  expect(theirs.xp.total).toBe(0);

  // A's course id, as A sees it; B's direct requests to it are 404, never 403.
  const bToken = await token(page);
  await page.getByRole("button", { name: "Account" }).click();
  await page.getByRole("button", { name: "Sign out" }).click();
  await signIn(page);
  const courses = await apiGet<{ id: string; title: string }[]>(page, "/api/v1/courses");
  const demo = courses.find((c) => c.title === COURSE)!;
  const documents = await apiGet<{ id: string }[]>(page, `/api/v1/courses/${demo.id}/documents`);
  for (const path of [
    `/api/v1/courses/${demo.id}`,
    `/api/v1/courses/${demo.id}/summary`,
    `/api/v1/courses/${demo.id}/outline`,
    `/api/v1/documents/${documents[0]!.id}/file`,
  ]) {
    const response = await page.request.get(path, { headers: { Authorization: `Bearer ${bToken}` } });
    expect(response.status(), path).toBe(404);
  }

  // Switching back to B in the same tab shows none of A's cached data.
  await page.getByRole("button", { name: "Account" }).click();
  await page.getByRole("button", { name: "Sign out" }).click();
  await signIn(page, email, password);
  await expect(page.getByText("Start your first course")).toBeVisible();
  await expect(page.getByText(COURSE)).toHaveCount(0);
});

test("curriculum loop: new course → chapter → upload → AI proposal → edit → accept", async ({ page }) => {
  await signIn(page);
  const title = `E2E course ${Date.now()}`;

  await page.getByRole("link", { name: "Courses" }).click();
  await page.getByRole("button", { name: "+ New course" }).click();
  await page.getByLabel("Title").fill(title);
  await page.getByRole("button", { name: "Create course" }).click();
  await expect(page.getByRole("navigation", { name: "Curriculum" }).getByRole("link", { name: title })).toBeVisible();

  await page.getByLabel("New chapter title").fill("Garanzie");
  await page.getByRole("button", { name: "Add chapter" }).click();
  await page.getByRole("navigation", { name: "Curriculum" }).getByRole("link", { name: "Garanzie" }).click();

  await page.getByTestId("material-input").setInputFiles({
    name: "garanzie.md",
    mimeType: "text/markdown",
    buffer: Buffer.from(
      "# La fideiussione\n\nLa fideiussione e il contratto con cui un terzo garantisce l'adempimento di un'obbligazione altrui.\n\n" +
        "# Il pegno\n\nIl pegno e una garanzia reale su beni mobili consegnati al creditore.\n",
    ),
  });
  await expect(page.getByText("Ready")).toBeVisible({ timeout: 30_000 });

  await page.getByRole("button", { name: "Analyze new material" }).click();
  const topicTitle = page.getByLabel("Topic title").first();
  await expect(topicTitle).toBeVisible({ timeout: 30_000 });
  await topicTitle.fill("Garanzie personali");
  await page.getByRole("button", { name: "Accept curriculum" }).click();

  await expect(page.getByRole("heading", { name: "Topics" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Curriculum" }).getByRole("link", { name: "Garanzie personali" })).toBeVisible();
});
