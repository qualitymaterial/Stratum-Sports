import { DOCS_LAST_UPDATED } from "@/app/docs/docsConfig";

export default function DocsPage({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <article className="rounded-lg border border-borderTone bg-panel p-6 shadow-terminal md:p-8">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
        <p className="mt-3 max-w-3xl text-sm leading-7 text-textMute">{description}</p>
        <p className="mt-3 text-xs uppercase tracking-[0.18em] text-textMute">
          Last updated: {DOCS_LAST_UPDATED}
        </p>
      </header>
      <div className="mt-8 space-y-8 text-sm leading-7">{children}</div>
    </article>
  );
}
