import { useId, useState } from "react";
import { useI18n } from "../../i18n";

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
  const { t } = useI18n();
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
      <h3>{t("dispute.title")}</h3>
      {testAi && (
        <p className="banner warning" role="note">
          {t("dispute.testAi")}
        </p>
      )}
      <label htmlFor={id}>{t("dispute.why")}</label>
      <textarea
        id={id}
        rows={3}
        maxLength={1000}
        value={argument}
        onChange={(e) => setArgument(e.target.value)}
        placeholder={t("dispute.placeholder")}
      />
      <p className="hint">{t("dispute.hint")}</p>
      <button type="submit" disabled={working || !ready}>
        {working ? t("dispute.asking") : t("dispute.ask")}
      </button>
    </form>
  );
}
