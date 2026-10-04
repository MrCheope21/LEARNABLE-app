import { useId, useState } from "react";

const MIN_LENGTH = 3;

/** "Ask the AI to look again": the objection goes to the evaluator; no grade changes. */
export function DisputeForm({
  working,
  onAsk,
  testAi = false,
}: {
  working: boolean;
  onAsk: (argument: string) => Promise<void>;
  testAi?: boolean;
}) {
  const [argument, setArgument] = useState("");
  const id = useId();
  const ready = argument.trim().length >= MIN_LENGTH;
  return (
    <form
      className="dispute"
      onSubmit={(event) => {
        event.preventDefault();
        if (ready) void onAsk(argument.trim());
      }}
    >
      <h3>Ask the AI to look again</h3>
      {testAi && (
        <p className="banner warning" role="note">
          The test AI can't read your objection: a second opinion would repeat the same grade. Grade it yourself below.
        </p>
      )}
      <label htmlFor={id}>Why do you disagree?</label>
      <textarea
        id={id}
        rows={3}
        maxLength={1000}
        value={argument}
        onChange={(e) => setArgument(e.target.value)}
        placeholder="Say what the evaluation got wrong…"
      />
      <p className="hint">
        The AI sees your objection and evaluates again. Both opinions stay visible; your grade changes only if you
        choose it below.
      </p>
      <button type="submit" disabled={working || !ready}>
        {working ? "Asking…" : "Ask for a second opinion"}
      </button>
    </form>
  );
}
