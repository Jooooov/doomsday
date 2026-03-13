"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useAuthStore } from "@/lib/store";

export default function RegisterPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { setAuth } = useAuthStore();
  const router = useRouter();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await api.register(email, password, "pt");
      setAuth(res.access_token, res.user);
      router.push("/dashboard");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="w-full max-w-sm bg-[#111] border border-[#222] rounded-xl p-8">
        <h1 className="text-xl font-bold mb-6">Create your account</h1>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm text-gray-400 mb-1">Email</label>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required
              className="w-full bg-[#0a0a0a] border border-[#222] rounded-lg px-3 py-2 text-sm text-gray-200" />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">Password</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
              required minLength={8}
              className="w-full bg-[#0a0a0a] border border-[#222] rounded-lg px-3 py-2 text-sm text-gray-200" />
          </div>
          {error && <p className="text-red-400 text-sm">{error}</p>}
          <button type="submit" disabled={loading}
            className="w-full py-2.5 bg-red-600 hover:bg-red-500 disabled:opacity-50 text-white rounded-lg font-medium text-sm transition-colors">
            {loading ? "Creating account..." : "Create Account"}
          </button>
        </form>
        <p className="text-center text-xs text-gray-500 mt-4">
          Already have an account?{" "}
          <a href="/login" className="text-gray-400 hover:text-gray-300">Sign in</a>
        </p>
        <div className="mt-4 pt-4 border-t border-[#222]">
          <a href="/api/auth/google"
            className="flex items-center justify-center w-full py-2 border border-[#222] rounded-lg text-sm text-gray-300 hover:bg-[#0a0a0a] transition-colors">
            Continue with Google
          </a>
        </div>
        <p className="mt-6 text-xs text-gray-600 disclaimer">
          This platform provides informational content only. Not a substitute for official civil protection guidance.
        </p>
      </div>
    </div>
  );
}
