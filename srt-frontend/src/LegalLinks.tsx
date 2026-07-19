// Legal / info links shown in every footer (marketing pages and static content
// pages). Standalone module so the marketing footers can import it without
// pulling in the content-page components.

const LINKS: [string, string][] = [
  ["Privacy Policy", "/privacy/"],
  ["Terms", "/terms/"],
  ["Contact", "/contact/"],
  ["About", "/about/"],
];

export function LegalLinks({ className = "" }: { className?: string }) {
  return (
    <div
      className={`flex flex-wrap items-center gap-x-5 gap-y-2 text-sm ${className}`}
    >
      {LINKS.map(([label, href]) => (
        <a
          key={href}
          href={href}
          className="text-white/70 underline-offset-4 transition hover:text-white hover:underline"
        >
          {label}
        </a>
      ))}
      <span className="text-white/40">© 2026 srt-flow</span>
    </div>
  );
}
