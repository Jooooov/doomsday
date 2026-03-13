import { CATEGORY_META } from "@/lib/categories";

export default function CategoryPreview() {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
      {CATEGORY_META.map((cat) => (
        <div key={cat.id}
          className="p-4 bg-[#111] border border-[#222] rounded-lg hover:border-gray-500 transition-colors">
          <div className="text-2xl mb-2">{cat.icon}</div>
          <div className="text-sm font-medium text-gray-200">{cat.label}</div>
          <div className="text-xs text-gray-500 mt-1">{cat.preview}</div>
        </div>
      ))}
    </div>
  );
}
