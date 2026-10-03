import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { mockApi, ok, sequence } from "../../test/mockApi";
import { fixtures } from "../../test/fixtures";
import { renderApp } from "../../test/render";

const course = fixtures.session.course_id;

class FakeRecognition {
  static last: FakeRecognition | null = null;
  lang = "";
  continuous = false;
  interimResults = false;
  started = false;
  onresult: ((event: { resultIndex: number; results: unknown[] }) => void) | null = null;
  onend: (() => void) | null = null;
  onerror: ((event: { error: string }) => void) | null = null;
  constructor() {
    FakeRecognition.last = this;
  }
  start() {
    this.started = true;
  }
  stop() {
    this.started = false;
    this.onend?.();
  }
  abort() {
    this.started = false;
  }
  say(transcript: string, isFinal = true) {
    this.onresult?.({ resultIndex: 0, results: [{ isFinal, 0: { transcript } }] });
  }
}

function backend() {
  return mockApi([
    ["POST", /\/review-sessions$/, ok(fixtures.session)],
    ["GET", /\/review-sessions\/[^/]+\/next$/, sequence(fixtures.card_learn, fixtures.card_done)],
    ["POST", /\/review-sessions\/[^/]+\/answers$/, ok(fixtures.answer_result)],
    ["POST", /\/review-sessions\/[^/]+\/end$/, ok(fixtures.session)],
    ["GET", /\/courses\/[^/]+$/, ok({ id: course, title: "Diritto", language: "it" })],
  ]);
}

async function toQuestion() {
  const user = userEvent.setup();
  renderApp(`/study/${course}?intent=LEARN`);
  await user.click(await screen.findByRole("button", { name: /I'm ready/ }));
  return user;
}

afterEach(() => {
  delete (window as unknown as Record<string, unknown>).webkitSpeechRecognition;
  FakeRecognition.last = null;
});

describe("voice answers", () => {
  it("dictates into the answer box and records the answer as spoken", async () => {
    (window as unknown as Record<string, unknown>).webkitSpeechRecognition = FakeRecognition;
    const { requests } = backend();
    const user = await toQuestion();

    await user.click(screen.getByRole("button", { name: "Speak your answer" }));
    const recognition = FakeRecognition.last!;
    expect(recognition.started).toBe(true);
    expect(recognition.lang).toBe("it-IT");
    expect(screen.getByRole("button", { name: "Stop listening" })).toHaveAttribute("aria-pressed", "true");

    act(() => recognition.say("la banca acquista", false));
    expect(await screen.findByText("la banca acquista")).toBeInTheDocument();
    act(() => recognition.say(" la banca acquista la proprieta "));
    act(() => recognition.say("del denaro"));
    expect(screen.getByLabelText("Your answer")).toHaveValue("la banca acquista la proprieta del denaro");

    await user.click(screen.getByRole("button", { name: "Stop listening" }));
    expect(screen.getByRole("button", { name: "Speak your answer" })).toBeInTheDocument();
    await user.type(screen.getByLabelText("Your answer"), " e la restituisce");
    await user.keyboard("{Control>}{Enter}{/Control}");

    await screen.findByText("Good");
    expect(requests.find((r) => r.path.endsWith("/answers"))?.body).toMatchObject({
      text: "la banca acquista la proprieta del denaro e la restituisce",
      method: "VOICE",
    });
  });

  it("explains a blocked microphone and keeps typing possible", async () => {
    (window as unknown as Record<string, unknown>).webkitSpeechRecognition = FakeRecognition;
    const { requests } = backend();
    const user = await toQuestion();

    await user.click(screen.getByRole("button", { name: "Speak your answer" }));
    act(() => FakeRecognition.last!.onerror?.({ error: "not-allowed" }));
    expect(await screen.findByText(/microphone is blocked/)).toBeInTheDocument();
    act(() => FakeRecognition.last!.stop());

    await user.type(screen.getByLabelText("Your answer"), "typed answer");
    await user.keyboard("{Control>}{Enter}{/Control}");
    await screen.findByText("Good");
    expect(requests.find((r) => r.path.endsWith("/answers"))?.body).toMatchObject({ method: "TEXT" });
  });

  it("offers typing only when the browser can't recognise speech", async () => {
    backend();
    await toQuestion();
    expect(screen.queryByRole("button", { name: "Speak your answer" })).not.toBeInTheDocument();
    expect(screen.getByText(/Voice answers need Chrome, Edge or Safari/)).toBeInTheDocument();
  });
});
