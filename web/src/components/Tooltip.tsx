import { cloneElement, useEffect, useId, useRef, useState, type ReactElement } from "react";

/** How long the pointer (or focus) must rest on a control before its explanation appears. */
export const TOOLTIP_DELAY_MS = 900;

/**
 * An explanation that appears only when someone lingers on a control: a quick click never shows
 * it, a hesitating pointer does. Keyboard focus works the same way, Escape hides it, and screen
 * readers always get the text (aria-describedby), without waiting.
 */
export function Tooltip({ text, children }: { text: string; children: ReactElement<{ "aria-describedby"?: string }> }) {
  const id = useId();
  const [visible, setVisible] = useState(false);
  const timer = useRef<number | undefined>(undefined);
  const show = () => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setVisible(true), TOOLTIP_DELAY_MS);
  };
  const hide = () => {
    window.clearTimeout(timer.current);
    setVisible(false);
  };
  useEffect(() => () => window.clearTimeout(timer.current), []);
  return (
    <span
      className="tooltip-anchor"
      onPointerEnter={(e) => e.pointerType !== "touch" && show()}
      onPointerLeave={hide}
      onPointerDown={hide}
      onFocus={show}
      onBlur={hide}
      onKeyDown={(e) => e.key === "Escape" && hide()}
    >
      {cloneElement(children, { "aria-describedby": id })}
      <span id={id} role="tooltip" className={visible ? "tooltip visible" : "tooltip"}>
        {text}
      </span>
    </span>
  );
}
