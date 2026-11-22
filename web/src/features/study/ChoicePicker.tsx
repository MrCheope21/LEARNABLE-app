import { useEffect, useMemo } from "react";
import { useI18n } from "../../i18n";

const LETTERS = "ABCDEFGH";

/** The same order for the same question on every render, a different one per question. */
export function shuffledOrder(count: number, seed: string): number[] {
  let state = 0;
  for (const ch of seed) state = (state * 31 + ch.charCodeAt(0)) >>> 0;
  const order = Array.from({ length: count }, (_, i) => i);
  for (let i = order.length - 1; i > 0; i -= 1) {
    state = (state * 1664525 + 1013904223) >>> 0;
    const j = state % (i + 1);
    [order[i], order[j]] = [order[j] as number, order[i] as number];
  }
  return order;
}

/**
 * A multiple-choice question's options, shuffled, as radio buttons (one correct option) or check
 * boxes (several). Keys 1-8 pick an option. `picked` holds positions in the original list.
 */
export function ChoicePicker({
  questionId,
  choices,
  multiple,
  picked,
  onChange,
  disabled,
}: {
  questionId: string;
  choices: string[];
  multiple: boolean;
  picked: number[];
  onChange: (picked: number[]) => void;
  disabled?: boolean;
}) {
  const { t } = useI18n();
  const order = useMemo(() => shuffledOrder(choices.length, questionId), [choices.length, questionId]);
  const toggle = (index: number) => {
    if (disabled) return;
    if (!multiple) onChange([index]);
    else onChange(picked.includes(index) ? picked.filter((i) => i !== index) : [...picked, index]);
  };
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLElement && /^(INPUT|TEXTAREA|SELECT)$/.test(event.target.tagName) && event.target.getAttribute("type") !== "radio" && event.target.getAttribute("type") !== "checkbox") return;
      const n = Number(event.key);
      if (Number.isInteger(n) && n >= 1 && n <= order.length) {
        event.preventDefault();
        toggle(order[n - 1] as number);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });
  return (
    <fieldset className="choices" disabled={disabled}>
      <legend className="hint">{multiple ? t("choice.pickAll") : t("choice.pickOne")}</legend>
      {order.map((index, position) => (
        <label key={index} className={picked.includes(index) ? "choice-option picked" : "choice-option"}>
          <input
            type={multiple ? "checkbox" : "radio"}
            name={`choice-${questionId}`}
            checked={picked.includes(index)}
            onChange={() => toggle(index)}
          />
          <span className="choice-letter" aria-hidden="true">
            {LETTERS[position]}
          </span>
          <span className="choice-text">{choices[index]}</span>
        </label>
      ))}
    </fieldset>
  );
}
