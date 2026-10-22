"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui-client";
import { errorMessage } from "@/lib/api";

const input = "mt-1 block w-full rounded-md border border-line bg-canvas px-3 py-2";

/** Sign in to a profile that has a password, from any browser. */
export function SignIn() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const res = await fetch("/api/profile/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    }).catch(() => null);
    setBusy(false);
    if (!res?.ok) {
      setError(errorMessage(await res?.json().catch(() => null), "Could not sign in."));
      return;
    }
    setPassword("");
    router.refresh();
  }

  return (
    <form
      onSubmit={submit}
      className="max-w-xl space-y-4 rounded-lg border border-line bg-surface p-5"
      aria-labelledby="signin-title"
    >
      <div>
        <h2 id="signin-title" className="font-semibold">
          Already have a profile?
        </h2>
        <p className="mt-1 text-sm text-ink-muted">
          Sign in with the email and password you set in Settings.
        </p>
      </div>
      <label className="block text-sm">
        <span className="font-medium">Email</span>
        <input
          type="email"
          required
          autoComplete="username"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className={input}
        />
      </label>
      <label className="block text-sm">
        <span className="font-medium">Password</span>
        <input
          type="password"
          required
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className={input}
        />
      </label>
      {error && (
        <p role="alert" className="text-sm text-bad">
          {error}
        </p>
      )}
      <Button type="submit" variant="secondary" disabled={busy}>
        {busy ? "Signing in…" : "Sign in"}
      </Button>
    </form>
  );
}
