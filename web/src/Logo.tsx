/** The Huddle mark: three people seen from above, leaning in. Drawn with the page's own colours so it follows light and dark. */
export default function Logo({ size = 28 }: { size?: number }) {
  return (
    <svg className="logo" width={size} height={size} viewBox="0 0 64 64" aria-hidden="true" focusable="false" fill="none" strokeWidth="8" strokeLinecap="round">
      <path d="M17.22 14.38A23 23 0 0 1 46.78 14.38" stroke="var(--lagoon)" />
      <circle cx="32.0" cy="22.0" r="5.6" fill="var(--lagoon)" />
      <path d="M54.65 28.01A23 23 0 0 1 39.87 53.61" stroke="var(--dusk)" />
      <circle cx="40.66" cy="37.0" r="5.6" fill="var(--dusk)" />
      <path d="M24.13 53.61A23 23 0 0 1 9.35 28.01" stroke="var(--saffron)" />
      <circle cx="23.34" cy="37.0" r="5.6" fill="var(--saffron)" />
    </svg>
  );
}

/** The mark next to the name, for the top of a page. */
export function Brand() {
  return <span className="brand"><Logo />Huddle</span>;
}
