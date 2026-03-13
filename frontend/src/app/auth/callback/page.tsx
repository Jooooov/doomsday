"use client";
import { Suspense, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuthStore } from "@/lib/store";
import { api } from "@/lib/api";

function CallbackInner() {
  const router = useRouter();
  const params = useSearchParams();
  const { setAuth } = useAuthStore();

  useEffect(() => {
    const token = params?.get("token");
    if (!token) { router.push("/login"); return; }
    if (typeof window !== "undefined") localStorage.setItem("doomsday_token", token);
    api.getMe().then((user) => {
      setAuth(token, user);
      router.push("/dashboard");
    }).catch(() => router.push("/login"));
  }, [params, router, setAuth]);

  return (
    <div className="min-h-screen flex items-center justify-center">
      <p className="text-gray-500 animate-pulse text-sm">Signing in...</p>
    </div>
  );
}

export default function AuthCallbackPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-gray-500 animate-pulse text-sm">Signing in...</p>
      </div>
    }>
      <CallbackInner />
    </Suspense>
  );
}
