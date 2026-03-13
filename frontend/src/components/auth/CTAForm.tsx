"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";

const COUNTRIES = [
  { code: "PT", name: "Portugal" }, { code: "US", name: "United States" },
  { code: "GB", name: "United Kingdom" }, { code: "DE", name: "Germany" },
  { code: "FR", name: "France" }, { code: "ES", name: "Spain" },
  { code: "BR", name: "Brazil" }, { code: "IT", name: "Italy" },
];

export default function CTAForm() {
  const [country, setCountry] = useState("PT");
  const [householdSize, setHouseholdSize] = useState(2);
  const router = useRouter();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (typeof window !== "undefined") {
      localStorage.setItem("doomsday_onboarding", JSON.stringify({ country, householdSize }));
    }
    router.push("/register");
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="block text-sm text-gray-400 mb-1">Your country</label>
        <select value={country} onChange={(e) => setCountry(e.target.value)}
          className="w-full bg-[#0a0a0a] border border-[#222] rounded-lg px-3 py-2 text-gray-200 text-sm">
          {COUNTRIES.map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}
        </select>
      </div>
      <div>
        <label className="block text-sm text-gray-400 mb-1">Household size</label>
        <select value={householdSize} onChange={(e) => setHouseholdSize(Number(e.target.value))}
          className="w-full bg-[#0a0a0a] border border-[#222] rounded-lg px-3 py-2 text-gray-200 text-sm">
          {[1,2,3,4,5,6,7,8].map((n) => (
            <option key={n} value={n}>{n} {n === 1 ? "person" : "people"}</option>
          ))}
        </select>
      </div>
      <button type="submit"
        className="w-full py-2.5 px-4 bg-red-600 hover:bg-red-500 text-white rounded-lg font-medium text-sm transition-colors">
        See My Preparation Guide →
      </button>
      <p className="text-xs text-gray-600 text-center">Free account required. No spam.</p>
    </form>
  );
}
