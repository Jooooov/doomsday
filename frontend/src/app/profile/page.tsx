"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useAuthStore } from "@/lib/store";

const COUNTRIES = [
  { code: "PT", name: "Portugal" }, { code: "US", name: "United States" },
  { code: "GB", name: "United Kingdom" }, { code: "DE", name: "Germany" },
  { code: "FR", name: "France" }, { code: "ES", name: "Spain" },
  { code: "BR", name: "Brazil" }, { code: "IT", name: "Italy" },
  { code: "NL", name: "Netherlands" }, { code: "PL", name: "Poland" },
];

const HOUSING_TYPES = [
  { value: "apartment_urban", label: "Urban apartment" },
  { value: "apartment_rural", label: "Rural apartment" },
  { value: "house_urban", label: "Urban house" },
  { value: "house_rural", label: "Rural house" },
];

export default function ProfilePage() {
  const { user, setAuth, token } = useAuthStore();
  const router = useRouter();
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const [form, setForm] = useState({
    country_code: user?.country_code || "PT",
    zip_code: user?.zip_code || "",
    household_size: user?.household_size || 2,
    housing_type: user?.housing_type || "apartment_urban",
    has_vehicle: false,
    language: user?.language || "pt",
    health_data_consent: false,
  });

  useEffect(() => { if (!user) router.push("/login"); }, [user, router]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const updated = await api.updateProfile(form);
      if (token) setAuth(token, updated);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="min-h-screen">
      <nav className="border-b border-[#222] px-4 py-3 flex justify-between items-center">
        <a href="/" className="font-bold text-sm">Doomsday Prep</a>
        <a href="/dashboard" className="text-sm text-gray-400 hover:text-gray-200">← Dashboard</a>
      </nav>

      <div className="max-w-lg mx-auto px-4 py-8">
        <h1 className="text-xl font-bold mb-6">Your Profile</h1>
        <form onSubmit={handleSave} className="space-y-5">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">Country</label>
              <select value={form.country_code}
                onChange={(e) => setForm({ ...form, country_code: e.target.value })}
                className="w-full bg-[#0a0a0a] border border-[#222] rounded-lg px-3 py-2 text-sm text-gray-200">
                {COUNTRIES.map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">ZIP / Postal code</label>
              <input value={form.zip_code}
                onChange={(e) => setForm({ ...form, zip_code: e.target.value })}
                placeholder="e.g. 1000-001"
                className="w-full bg-[#0a0a0a] border border-[#222] rounded-lg px-3 py-2 text-sm text-gray-200" />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">Household size</label>
              <select value={form.household_size}
                onChange={(e) => setForm({ ...form, household_size: Number(e.target.value) })}
                className="w-full bg-[#0a0a0a] border border-[#222] rounded-lg px-3 py-2 text-sm text-gray-200">
                {[1,2,3,4,5,6,7,8].map((n) => (
                  <option key={n} value={n}>{n} {n === 1 ? "person" : "people"}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Housing type</label>
              <select value={form.housing_type}
                onChange={(e) => setForm({ ...form, housing_type: e.target.value })}
                className="w-full bg-[#0a0a0a] border border-[#222] rounded-lg px-3 py-2 text-sm text-gray-200">
                {HOUSING_TYPES.map((h) => <option key={h.value} value={h.value}>{h.label}</option>)}
              </select>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <input type="checkbox" id="vehicle" checked={form.has_vehicle}
              onChange={(e) => setForm({ ...form, has_vehicle: e.target.checked })}
              className="accent-red-500" />
            <label htmlFor="vehicle" className="text-sm text-gray-300">I have access to a vehicle</label>
          </div>

          <div className="flex items-center gap-3">
            <input type="checkbox" id="health_consent" checked={form.health_data_consent}
              onChange={(e) => setForm({ ...form, health_data_consent: e.target.checked })}
              className="accent-red-500" />
            <label htmlFor="health_consent" className="text-sm text-gray-300">
              I consent to storing my health conditions for personalized guide recommendations
              <span className="block text-xs text-gray-500 mt-0.5">GDPR: stored encrypted, deletable at any time</span>
            </label>
          </div>

          <button type="submit" disabled={saving}
            className="w-full py-2.5 bg-red-600 hover:bg-red-500 disabled:opacity-50 text-white rounded-lg font-medium text-sm transition-colors">
            {saving ? "Saving..." : saved ? "Saved ✓" : "Save Profile"}
          </button>
        </form>
      </div>
    </div>
  );
}
