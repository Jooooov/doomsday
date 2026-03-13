import { CATEGORY_META } from "@/lib/categories";

export default function CategoryPreview() {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
      {CATEGORY_META.map((cat) => (
        <div key={cat.id} className="pip-panel p-4 group cursor-default transition-all hover:shadow-[0_0_20px_rgba(89,255,89,0.1)]">
          {/* Fallout terminal icon */}
          <div
            className="font-fallout text-4xl leading-none mb-3 select-none"
            style={{
              color: "var(--pip-bright)",
              textShadow: "0 0 6px var(--pip-green), 0 0 18px var(--pip-green)",
            }}
          >
            {cat.icon}
          </div>
          <div
            className="text-xs font-fallout uppercase tracking-[0.12em] mb-1"
            style={{ color: "var(--pip-bright)" }}
          >
            {cat.label}
          </div>
          <div className="text-xs leading-relaxed" style={{ color: "var(--pip-dim)" }}>
            {cat.preview}
          </div>
        </div>
      ))}
    </div>
  );
}
