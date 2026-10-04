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
  // Opens towards the end side unless that would leave the screen (a button near the edge).
  const [toStart, setToStart] = useState(false);
  const anchor = useRef<HTMLSpanElement>(null);
  const timer = useRef<number | undefined>(undefined);
  const show = () => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      const box = anchor.current?.getBoundingClientRect();
      const width = Math.min(280, window.innerWidth * 0.8);
      const rtl = document.documentElement.dir === "rtl";
      setToStart(Boolean(box && (rtl ? box.right - width < 8 : box.left + width > window.innerWidth - 8)));
      setVisible(true);
    }, TOOLTIP_DELAY_MS);
  };
  const hide = () => {
    window.clearTimeout(timer.current);
    setVisible(false);
  };
  useEffect(() => () => window.clearTimeout(timer.current), []);
  return (
    <span
      ref={anchor}
      className="tooltip-anchor"
      onPointerEnter={(e) => e.pointerType !== "touch" && show()}
      onPointerLeave={hide}
      onPointerDown={hide}
      onFocus={show}
      onBlur={hide}
      onKeyDown={(e) => e.key === "Escape" && hide()}
    >
      {cloneElement(children, { "aria-describedby": id })}
      <span id={id} role="tooltip" className={["tooltip", visible && "visible", toStart && "flip"].filter(Boolean).join(" ")}>
        {text}
      </span>
    </span>
  );
}
