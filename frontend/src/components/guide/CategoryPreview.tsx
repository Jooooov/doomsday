import { CATEGORY_META } from "@/lib/categories";

export default function CategoryPreview() {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
      {CATEGORY_META.map((cat) => (
        <div key={cat.id} className="pip-panel p-4 group cursor-default transition-all hover:shadow-[0_0_20px_rgba(89,255,89,0.08)]">
          {/* Category icon */}
          <div
            className="text-3xl leading-none mb-3 select-none flex items-center justify-center rounded-lg"
            style={{
              width: 48, height: 48,
              background: `${cat.color}18`,
              border: `1.5px solid ${cat.color}55`,
              boxShadow: `0 0 12px ${cat.color}22`,
            }}
          >
            {cat.icon}
          </div>
          <div
            className="text-xs uppercase tracking-[0.12em] mb-1 font-mono"
            style={{ color: cat.color }}
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
