"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { login } from "@/lib/api";
import { Button, ErrorBanner, Input } from "@/components/ui";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center px-6">
      <div className="w-full max-w-sm">
        <p className="mb-8 text-center font-mono text-lg font-medium text-ink">
          meet<span className="text-accent">graph</span>
        </p>
        <form
          onSubmit={submit}
          className="space-y-4 rounded-lg border border-edge bg-surface p-6"
        >
          <h1 className="text-base font-semibold text-ink">Sign in</h1>
          {error && <ErrorBanner message={error} />}
          <Input
            type="email"
            placeholder="you@company.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoFocus
          />
          <Input
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
          <Button type="submit" disabled={busy} className="w-full">
            {busy ? "Signing in…" : "Sign in"}
          </Button>
          <p className="text-center text-xs text-faint">
            No account?{" "}
            <Link href="/register" className="text-info hover:underline">
              Register
            </Link>
          </p>
        </form>
      </div>
    </div>
  );
}
