import { useI18n } from "../i18n";

const STAR = "M12 3.2l2.7 5.6 6.1.8-4.5 4.3 1.1 6.1L12 17.1 6.6 20l1.1-6.1L3.2 9.6l6.1-.8z";

function Star({ fill, size }: { fill: number; size: number }) {
  // `fill` between 0 and 1: the part of the star that is coloured.
  return (
    <span className="star" style={{ width: size, height: size }} aria-hidden="true">
      <svg width={size} height={size} viewBox="0 0 24 24" focusable="false">
        <path d={STAR} className="star-empty" />
      </svg>
      {fill > 0 && (
        <span className="star-fill" style={{ width: `${fill * 100}%` }}>
          <svg width={size} height={size} viewBox="0 0 24 24" focusable="false">
            <path d={STAR} />
          </svg>
        </span>
      )}
    </span>
  );
}

/** A rating out of five, read aloud as "4.5 out of 5 stars". */
export function Stars({ value, size = 16 }: { value: number; size?: number }) {
  const { t } = useI18n();
  return (
    <span className="stars" role="img" aria-label={t("review.outOf", { n: value.toLocaleString(undefined, { maximumFractionDigits: 1 }) })}>
      {[0, 1, 2, 3, 4].map((i) => (
        <Star key={i} size={size} fill={Math.max(0, Math.min(1, value - i))} />
      ))}
    </span>
  );
}

/** Five buttons to choose a rating (1-5), usable with the keyboard like radio buttons. */
export function StarInput({ value, onChange, label }: { value: number; onChange: (value: number) => void; label: string }) {
  const { t } = useI18n();
  return (
    <div className="star-input" role="radiogroup" aria-label={label}>
      {[1, 2, 3, 4, 5].map((n) => (
        <button key={n} type="button" role="radio" aria-checked={value === n} aria-label={t("review.stars", { n })} className={n <= value ? "on" : undefined} onClick={() => onChange(n)}>
          <svg width={30} height={30} viewBox="0 0 24 24" aria-hidden="true" focusable="false">
            <path d={STAR} />
          </svg>
        </button>
      ))}
    </div>
  );
}
