import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Schemas } from "../../api/client";
import { fixtures } from "../../test/fixtures";
import { mockApi, ok } from "../../test/mockApi";
import { renderApp } from "../../test/render";

const course = fixtures.concept.course_id;
const outline = fixtures.outline;
const chapter = outline[0]!;
const topic = chapter.topics[0]!;
const concept = topic.concepts[0]!;
const base = fixtures.learning_items[0]!;

function itemFixture(id: string, text: string): Schemas["LearningItemRead"] {
  return {
    ...base,
    id,
    concept_id: concept.id,
    topic_id: topic.id,
    chapter_id: chapter.id,
    title: text,
    questions: [{ ...base.questions[0]!, id: `${id}-q`, text }],
  };
}

const items = [itemFixture("i1", "Che cos'è il mutuo?"), itemFixture("i2", "Che cos'è il deposito?")];

function backend() {
  return mockApi([
    ["GET", /\/courses\/[^/]+\/outline$/, ok(outline)],
    ["GET", /\/courses\/[^/]+\/learning-items$/, ok(items)],
    ["GET", /\/courses\/[^/]+$/, ok({ id: course, title: "Diritto bancario" })],
    ["POST", /\/learning-items\/bulk$/, ok({ affected: 2, created_concepts: 0, deleted_concepts: 1 })],
    ["POST", /\/curriculum\/bulk-delete$/, ok({ chapters: 1, topics: 0, concepts: 0, items: 0 })],
    ["PATCH", /\/learning-items\/[^/]+$/, ok(items[0])],
    ["PATCH", /\/questions\/[^/]+$/, ok(items[0]!.questions[0])],
  ]);
}

describe("question manager", () => {
  it("moves several questions at once into another concept", async () => {
    const user = userEvent.setup();
    const { requests } = backend();
    renderApp(`/courses/${course}/questions`);

    await user.click(await screen.findByRole("checkbox", { name: "Select: Che cos'è il mutuo?" }));
    await user.click(screen.getByRole("checkbox", { name: "Select: Che cos'è il deposito?" }));
    const bar = screen.getByRole("toolbar", { name: "Selected questions" });
    expect(bar).toHaveTextContent("2 selected");
    await user.click(within(bar).getByRole("button", { name: "Move to…" }));
    await user.selectOptions(screen.getByLabelText(/Move 2 questions to/), `concept:${concept.id}`);
    await user.click(screen.getByRole("button", { name: "Move" }));

    await waitFor(() =>
      expect(requests.find((r) => r.path.endsWith("/bulk"))?.body).toEqual({
        item_ids: ["i1", "i2"],
        action: "move",
        target_concept_id: concept.id,
        delete_emptied_concepts: true,
      }),
    );
    expect(await screen.findByText(/Moved 2 questions · 1 empty concept removed/)).toBeInTheDocument();
  });

  it("deletes a whole group with its questions, in every stage, after confirming", async () => {
    const user = userEvent.setup();
    const { requests } = backend();
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    renderApp(`/courses/${course}/questions`);

    await user.click(await screen.findByRole("checkbox", { name: `Select every question in ${chapter.title}` }));
    expect(screen.getByRole("checkbox", { name: `Select every question in ${topic.title}` })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: `Select every question in ${concept.title}` })).toBeChecked();
    await user.click(screen.getByRole("button", { name: "Delete" }));
    expect(confirm).toHaveBeenCalledWith(expect.stringMatching(/Delete 2 questions.*1 chapter.*deleted too/));
    await waitFor(() =>
      expect(requests.find((r) => r.path.endsWith("/curriculum/bulk-delete"))?.body).toEqual({
        chapter_ids: [chapter.id],
        topic_ids: [],
        concept_ids: [],
        item_ids: [],
      }),
    );
    expect(await screen.findByText(/Deleted 2 questions and 1 emptied group/)).toBeInTheDocument();
    confirm.mockRestore();
  });

  it("deletes only the questions chosen when the group is not fully selected", async () => {
    const user = userEvent.setup();
    const { requests } = backend();
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    renderApp(`/courses/${course}/questions`);

    await user.click(await screen.findByRole("checkbox", { name: "Select: Che cos'è il mutuo?" }));
    expect(screen.getByRole("checkbox", { name: `Select every question in ${concept.title}` })).not.toBeChecked();
    await user.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() =>
      expect(requests.find((r) => r.path.endsWith("/curriculum/bulk-delete"))?.body).toEqual({
        chapter_ids: [],
        topic_ids: [],
        concept_ids: [],
        item_ids: ["i1"],
      }),
    );
    confirm.mockRestore();
  });

  it("selects and deselects everything with one button", async () => {
    const user = userEvent.setup();
    backend();
    renderApp(`/courses/${course}/questions`);

    await user.click(await screen.findByRole("button", { name: "Select all (2)" }));
    expect(screen.getByRole("toolbar", { name: "Selected questions" })).toHaveTextContent("2 selected");
    await user.click(screen.getByRole("button", { name: "Deselect all" }));
    expect(screen.queryByRole("toolbar", { name: "Selected questions" })).not.toBeInTheDocument();
  });

  it("edits one question's wording and expected answer", async () => {
    const user = userEvent.setup();
    const { requests } = backend();
    renderApp(`/courses/${course}/questions`);

    const edit = await screen.findAllByRole("button", { name: "Edit" });
    await user.click(edit[0]!);
    const form = screen.getByRole("form", { name: "Edit question" });
    const wording = within(form).getByLabelText("Wording 1");
    await user.clear(wording);
    await user.type(wording, "Definisci il mutuo.");
    const answer = within(form).getByLabelText("Expected answer");
    await user.clear(answer);
    await user.type(answer, "Consegna di denaro con obbligo di restituzione.");
    await user.click(within(form).getByRole("button", { name: "Save" }));

    await waitFor(() => expect(requests.find((r) => r.method === "PATCH" && r.path.includes("/questions/"))?.body).toEqual({ text: "Definisci il mutuo." }));
    expect(requests.find((r) => r.method === "PATCH" && r.path.includes("/learning-items/"))?.body).toMatchObject({
      expected_knowledge: "Consegna di denaro con obbligo di restituzione.",
    });
  });
});

describe("rename", () => {
  it("renames a topic in place", async () => {
    const user = userEvent.setup();
    const { requests } = mockApi([
      ["GET", /\/courses\/[^/]+\/outline$/, ok(outline)],
      ["GET", /\/courses\/[^/]+\/progress$/, ok(fixtures.progress)],
      ["GET", /\/courses\/[^/]+$/, ok({ id: course, title: "Diritto bancario" })],
      ["PATCH", /\/topics\/[^/]+$/, ok({ ...topic, title: "Contratti di deposito" })],
    ]);
    renderApp(`/courses/${course}/topics/${topic.id}`);

    await user.click(await screen.findByRole("button", { name: "Rename topic" }));
    const title = screen.getByLabelText("Title");
    await user.clear(title);
    await user.type(title, "Contratti di deposito");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(requests.find((r) => r.method === "PATCH")?.body).toEqual({ title: "Contratti di deposito", description: topic.description ?? "" }),
    );
  });
});

describe("paste text", () => {
  it("adds pasted text as a Markdown upload with the chosen purpose", async () => {
    const user = userEvent.setup();
    const { fetchMock } = mockApi([
      ["GET", /\/courses\/[^/]+\/documents$/, ok([])],
      ["POST", /\/courses\/[^/]+\/documents$/, ok({ id: "d1", status: "PROCESSING" })],
      ["GET", /\/courses\/[^/]+\/outline$/, ok(outline)],
      ["GET", /\/courses\/[^/]+$/, ok({ id: course, title: "Diritto bancario" })],
    ]);
    renderApp(`/courses/${course}/material`);

    await user.click(await screen.findByRole("button", { name: "Paste text" }));
    const form = screen.getByRole("form", { name: "Paste text" });
    await user.type(within(form).getByLabelText("Title"), "Appunti lezione 3");
    await user.click(within(form).getByLabelText(/Questions & answers/));
    await user.type(within(form).getByLabelText("Text"), "Domanda: Che cos'è?{enter}Risposta: Una cosa.");
    await user.click(within(form).getByRole("button", { name: "Add text" }));

    await waitFor(() => expect(fetchMock.mock.calls.some(([input]) => String(input instanceof Request ? input.url : input).endsWith("/documents"))).toBe(true));
    const upload = fetchMock.mock.calls.find(([input, init]) => {
      const url = String(input instanceof Request ? input.url : input);
      return url.endsWith("/documents") && (init?.method ?? (input instanceof Request ? input.method : "GET")) === "POST";
    });
    const body = (upload?.[1] as RequestInit | undefined)?.body as FormData;
    const file = body.get("file") as File;
    expect(file.name).toBe("Appunti lezione 3.md");
    expect(await file.text()).toBe("Domanda: Che cos'è?\nRisposta: Una cosa.");
    expect(body.get("purpose")).toBe("QUESTION_BANK");
  });
});
