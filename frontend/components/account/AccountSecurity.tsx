"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui-client";
import { errorMessage, type Profile } from "@/lib/api";

const input = "mt-1 block w-full rounded-md border border-line bg-canvas px-3 py-2";

/** Set or change the profile's password, and sign out. */
export function AccountSecurity({ profile }: { profile: Profile }) {
  const router = useRouter();
  const [email, setEmail] = useState(profile.email ?? "");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [current, setCurrent] = useState("");
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const has = profile.has_password;

  async function call(path: string, method: string, body: unknown) {
    setBusy(true);
    setMessage(null);
    const res = await fetch(path, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).catch(() => null);
    setBusy(false);
    if (!res?.ok) {
      setMessage({
        ok: false,
        text: errorMessage(await res?.json().catch(() => null), "Something went wrong."),
      });
      return false;
    }
    return true;
  }

  async function save(e: FormEvent) {
    e.preventDefault();
    if (password !== confirm) {
      setMessage({ ok: false, text: "The two passwords do not match." });
      return;
    }
    const ok = await call("/api/profile/credentials", "PUT", {
      email,
      password,
      current_password: has ? current : null,
    });
    if (ok) {
      setPassword("");
      setConfirm("");
      setCurrent("");
      setMessage({
        ok: true,
        text: has
          ? "Password changed. Other browsers have been signed out."
          : "Password set. You can now sign in from another browser.",
      });
      router.refresh();
    }
  }

  async function signOut(everywhere: boolean) {
    if (await call("/api/profile/logout", "POST", { everywhere })) {
      router.push("/academics");
      router.refresh();
    }
  }

  return (
    <div className="space-y-4 text-sm">
      <p className="text-ink-muted">
        {has
          ? `Signed in with ${profile.email}. Your password protects this profile on other browsers.`
          : "This profile lives only in this browser's cookie. Set a password to sign in elsewhere and to be able to sign out on a shared device. The email is only a sign-in name; nothing is sent to it."}
      </p>
      <form onSubmit={save} className="space-y-3">
        <label className="block">
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
        {has && (
          <label className="block">
            <span className="font-medium">Current password</span>
            <input
              type="password"
              required
              autoComplete="current-password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
              className={input}
            />
          </label>
        )}
        <label className="block">
          <span className="font-medium">{has ? "New password" : "Password"}</span>
          <input
            type="password"
            required
            minLength={10}
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={input}
          />
          <span className="text-xs text-ink-muted">At least 10 characters.</span>
        </label>
        <label className="block">
          <span className="font-medium">Repeat password</span>
          <input
            type="password"
            required
            autoComplete="new-password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            className={input}
          />
        </label>
        <Button type="submit" variant="secondary" disabled={busy}>
          {has ? "Change password" : "Set password"}
        </Button>
      </form>
      {has && (
        <div className="flex flex-wrap gap-2 border-t border-line pt-4">
          <Button variant="secondary" disabled={busy} onClick={() => void signOut(false)}>
            Sign out
          </Button>
          <Button variant="secondary" disabled={busy} onClick={() => void signOut(true)}>
            Sign out everywhere
          </Button>
        </div>
      )}
      {message && (
        <p role={message.ok ? "status" : "alert"} className={message.ok ? "text-ok" : "text-bad"}>
          {message.text}
        </p>
      )}
    </div>
  );
}
