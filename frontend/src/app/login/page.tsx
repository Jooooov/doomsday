"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useAuthStore } from "@/lib/store";

export default function LoginPage() {
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
      const res = await api.login(email, password);
      setAuth(res.access_token, res.user);
      router.push("/dashboard");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Credenciais inválidas");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-4 pip-power-on">
      <a href="/" className="pip-glow font-fallout uppercase tracking-[0.2em] text-2xl mb-8 pip-flicker">
        ☢ DOOMSDAY PREP
      </a>

      <div className="w-full max-w-sm pip-panel p-8">
        <h1 className="pip-section text-base mb-6">Autenticação de Sobrevivente</h1>

        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label className="block text-xs uppercase tracking-widest mb-1" style={{ color: "var(--pip-dim)" }}>
              ▶ Identificação (Email)
            </label>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required
              className="pip-input w-full text-sm" placeholder="vault@dweller.pip" />
          </div>
          <div>
            <label className="block text-xs uppercase tracking-widest mb-1" style={{ color: "var(--pip-dim)" }}>
              ▶ Código de Acesso
            </label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required
              className="pip-input w-full text-sm" placeholder="••••••••" />
          </div>

          {error && (
            <div className="pip-badge-danger flex items-center gap-2">
              ⚠ {error}
            </div>
          )}

          <button type="submit" disabled={loading}
            className="pip-btn pip-btn-solid w-full py-2.5 text-sm tracking-[0.15em] disabled:opacity-40">
            {loading ? "VERIFICANDO..." : "ACEDER AO TERMINAL"}
          </button>
        </form>

        <hr className="pip-divider" />

        <p className="text-center text-xs tracking-wider" style={{ color: "var(--pip-dim)" }}>
          Sem conta?{" "}
          <a href="/register" className="pip-nav-link underline">Registar sobrevivente</a>
        </p>

        <div className="mt-4">
          <a href="/api/auth/google"
            className="pip-btn w-full flex items-center justify-center py-2 text-xs tracking-widest">
            CONTINUAR COM GOOGLE
          </a>
        </div>
      </div>
    </div>
  );
}
