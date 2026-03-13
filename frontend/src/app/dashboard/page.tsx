"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import { api, type GuideSection } from "@/lib/api";
import { useAuthStore } from "@/lib/store";
import { CATEGORY_META } from "@/lib/categories";

export default function DashboardPage() {
  const { user, clearAuth } = useAuthStore();
  const router = useRouter();

  useEffect(() => { if (!user) router.push("/login"); }, [user, router]);

  const { data: guide, mutate: mutateGuide } = useSWR(user ? "my-guide" : null, api.getMyGuide);
  const { data: group } = useSWR(user ? "my-group" : null, api.getMyGroup);
  const { data: checklist } = useSWR(user ? "group-checklist" : null, api.getGroupChecklist);

  if (!user) return null;

  const handleGenerateGuide = async () => {
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/guides/me/generate`, {
      method: "POST",
      headers: { Authorization: `Bearer ${localStorage.getItem("doomsday_token")}` },
    });
    const reader = res.body?.getReader();
    if (!reader) return;
    while (true) {
      const { done } = await reader.read();
      if (done) break;
    }
    mutateGuide();
  };

  return (
    <div className="min-h-screen">
      <nav className="border-b border-[#222] px-4 py-3 flex justify-between items-center">
        <a href="/" className="font-bold text-sm">Doomsday Prep</a>
        <div className="flex gap-4 text-sm">
          <a href="/" className="text-gray-400 hover:text-gray-200">World Map</a>
          <button onClick={() => { clearAuth(); router.push("/"); }}
            className="text-gray-500 hover:text-gray-300">Sign out</button>
        </div>
      </nav>

      <div className="max-w-7xl mx-auto px-4 py-8 grid lg:grid-cols-3 gap-8">
        {/* Guide section — 2/3 width */}
        <div className="lg:col-span-2">
          <div className="flex items-center gap-3 mb-4">
            <h1 className="text-xl font-bold">Your Preparation Guide</h1>
            {guide?.badge && (
              <span className="text-xs px-2 py-1 bg-yellow-900 text-yellow-200 rounded-full">{guide.badge}</span>
            )}
          </div>

          {!guide || guide.status === "pending" ? (
            <div className="p-6 bg-[#111] border border-[#222] rounded-xl text-center">
              <p className="text-gray-400 mb-4">No guide yet.</p>
              {!user.country_code && (
                <p className="text-xs text-gray-600 mb-3">Complete your profile first (country required).</p>
              )}
              <button onClick={handleGenerateGuide} disabled={!user.country_code}
                className="px-4 py-2 bg-red-600 hover:bg-red-500 disabled:opacity-40 text-white rounded-lg text-sm">
                Generate My Guide
              </button>
            </div>
          ) : guide.content ? (
            <GuideAccordion content={guide.content} />
          ) : null}
        </div>

        {/* Sidebar — 1/3 width */}
        <div className="space-y-6">
          {/* Family group */}
          <div className="p-4 bg-[#111] border border-[#222] rounded-xl">
            <h2 className="text-sm font-semibold mb-3">👨‍👩‍👧 Family Group</h2>
            {group && "group_id" in group ? (
              <div className="text-sm text-gray-300 space-y-1">
                <p>{group.member_count} members</p>
                {group.is_admin && (
                  <p className="text-xs text-gray-500 break-all">Invite: {group.invite_link}</p>
                )}
              </div>
            ) : (
              <button onClick={async () => {
                const g = await api.createGroup();
                alert(`Share: ${window.location.origin}${g.invite_link}`);
              }} className="text-xs text-gray-400 hover:text-gray-200 underline">
                Create family group
              </button>
            )}
          </div>

          {/* Checklist */}
          {checklist?.items && checklist.items.length > 0 && (
            <div className="p-4 bg-[#111] border border-[#222] rounded-xl">
              <h2 className="text-sm font-semibold mb-3">🏠 Family Checklist</h2>
              <div className="space-y-2">
                {checklist.items.slice(0, 8).map((item) => (
                  <label key={item.id} className="flex items-start gap-2 text-xs text-gray-400 cursor-pointer">
                    <input type="checkbox" checked={item.status === "complete"} readOnly
                      className="mt-0.5 accent-red-500" />
                    <span className={item.status === "complete" ? "line-through text-gray-600" : ""}>
                      {item.text}
                      {item.calculated_quantity && (
                        <span className="text-gray-600 ml-1">({item.calculated_quantity} {item.quantity_unit})</span>
                      )}
                    </span>
                  </label>
                ))}
              </div>
            </div>
          )}

          {/* GDPR actions */}
          <div className="p-4 bg-[#111] border border-[#222] rounded-xl">
            <h2 className="text-sm font-semibold mb-3">Privacy</h2>
            <div className="flex flex-col gap-2">
              <a href="/api/users/me/export"
                className="text-xs text-gray-400 hover:text-gray-200 underline">Export my data (JSON)</a>
              <button onClick={async () => {
                if (confirm("Delete your account permanently?")) {
                  await api.deleteAccount();
                  clearAuth();
                  router.push("/");
                }
              }} className="text-xs text-red-600 hover:text-red-400 underline text-left">
                Delete account
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function GuideAccordion({ content }: { content: Record<string, GuideSection> }) {
  const order = CATEGORY_META.map((c) => c.id);
  const sorted = [...Object.entries(content)].sort(
    ([a], [b]) => order.indexOf(a) - order.indexOf(b)
  );
  return (
    <div className="space-y-2">
      {sorted.map(([category, section]) => {
        const meta = CATEGORY_META.find((c) => c.id === category);
        return (
          <details key={category} className="bg-[#111] border border-[#222] rounded-xl group">
            <summary className="px-4 py-3 cursor-pointer text-sm font-medium flex items-center gap-2">
              <span>{meta?.icon}</span>
              <span>{section?.title || meta?.label || category.replace("_", " ")}</span>
            </summary>
            <div className="px-4 pb-4 space-y-2">
              {section?.items?.map((item, i) => (
                <div key={i} className="flex items-start gap-2 text-sm text-gray-300">
                  <span className="text-gray-600 text-xs mt-0.5">•</span>
                  <span>
                    {item.text}
                    {item.quantity && (
                      <span className="text-gray-500 ml-1">— {item.quantity} {item.unit}</span>
                    )}
                  </span>
                </div>
              ))}
              {section?.disclaimer && (
                <p className="disclaimer mt-3">{section.disclaimer}</p>
              )}
            </div>
          </details>
        );
      })}
    </div>
  );
}
