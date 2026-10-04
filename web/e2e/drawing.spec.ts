import { expect, test } from "@playwright/test";

// Drawing questions end to end: a reference drawing set on a question, the answer drawn with the
// mouse on the pad, both drawings shown side by side afterwards. Self-contained (own user).
const PASSWORD = "drawing-e2e-password";
// A tiny valid PNG (1x1 pixel).
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
  "base64",
);

test("a drawing question is answered by drawing and compared with its reference", async ({ page, request }) => {
  const email = `drawing-${Date.now()}@example.com`;
  expect((await request.post("/api/v1/auth/register", { data: { email, password: PASSWORD } })).status()).toBe(201);
  const token = ((await (await request.post("/api/v1/auth/login", { data: { email, password: PASSWORD } })).json()) as { access_token: string }).access_token;
  const headers = { Authorization: `Bearer ${token}` };
  const post = async (path: string, data: object) => ((await (await request.post(`/api/v1${path}`, { data, headers })).json()) as { id: string }).id;
  const course = await post("/courses", { title: "Chimica organica", language: "it" });
  const chapter = await post(`/courses/${course}/chapters`, { title: "Aromatici" });
  const topic = await post(`/chapters/${chapter}/topics`, { title: "Benzene" });
  const concept = await post(`/topics/${topic}/concepts`, { title: "Struttura del benzene" });
  const item = await post(`/concepts/${concept}/learning-items`, {
    title: "Formula del benzene",
    expected_knowledge: "Anello a sei atomi di carbonio con doppi legami alternati.",
    questions: [{ question_type: "RECALL", text: "Disegna la formula di struttura del benzene." }],
  });
  const uploaded = await request.put(`/api/v1/learning-items/${item}/reference-drawing`, {
    headers,
    multipart: { file: { name: "benzene.png", mimeType: "image/png", buffer: PNG } },
  });
  expect(uploaded.status()).toBe(200);
  expect(((await uploaded.json()) as { answer_format: string }).answer_format).toBe("DRAWING");
  await request.post(`/api/v1/concepts/${concept}/activate`, { headers });

  await page.goto("/");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible();
  await page.goto(`/courses/${course}/concepts/${concept}`);
  await page.getByRole("button", { name: "I have studied this concept" }).click();

  const canvas = page.getByRole("img", { name: /Drawing area/ });
  await expect(canvas).toBeVisible();
  const submit = page.getByRole("button", { name: /Submit/ });
  await expect(submit).toBeDisabled();
  const box = (await canvas.boundingBox())!;
  // A hexagon, drawn with the mouse.
  const cx = box.x + box.width / 2;
  const cy = box.y + box.height / 2;
  const r = Math.min(box.width, box.height) / 4;
  await page.mouse.move(cx + r, cy);
  await page.mouse.down();
  for (let i = 1; i <= 6; i++) {
    await page.mouse.move(cx + r * Math.cos((i * Math.PI) / 3), cy + r * Math.sin((i * Math.PI) / 3), { steps: 4 });
  }
  await page.mouse.up();
  await expect(submit).toBeEnabled();
  const answered = page.waitForResponse((r) => r.request().method() === "POST" && r.url().endsWith("/answers"));
  await submit.click();
  const sent = (await answered).request().postDataJSON() as { drawing: string; text: string };
  expect(sent.drawing).toMatch(/^data:image\/png;base64,/);

  const compare = page.getByRole("region", { name: "Your drawing and the reference" });
  await expect(compare.getByRole("img", { name: "Your drawing" })).toBeVisible();
  await expect(compare.getByRole("img", { name: "The reference drawing" })).toBeVisible();
  // The offline mock can't see images: it leaves the grade to the student.
  await expect(page.getByText("How well did you know it?")).toBeVisible();
});
