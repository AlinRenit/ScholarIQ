"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui-client";
import { errorMessage } from "@/lib/api";

export function CreateProfile() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [consent, setConsent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const res = await fetch("/api/profile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ display_name: name, consent }),
    }).catch(() => null);
    setBusy(false);
    if (!res?.ok) {
      setError(errorMessage(await res?.json().catch(() => null), "Could not create profile."));
      return;
    }
    router.refresh();
  }

  return (
    <form
      onSubmit={submit}
      className="max-w-xl space-y-4 rounded-lg border border-line bg-surface p-5"
    >
      <div>
        <h2 className="font-semibold">Create your local profile</h2>
        <p className="mt-1 text-sm text-ink-muted">
          Your profile stays on this ScholarIQ server and is tied to this browser. There is no
          password yet, so use ScholarIQ on a device you trust.
        </p>
      </div>
      <label className="block text-sm">
        <span className="font-medium">Name to show</span>
        <input
          required
          maxLength={120}
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="mt-1 block w-full rounded-md border border-line bg-canvas px-3 py-2"
        />
      </label>
      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          checked={consent}
          onChange={(e) => setConsent(e.target.checked)}
          className="mt-1"
        />
        <span className="text-ink-muted">
          I agree that ScholarIQ may store my marksheets and results on this server to analyse
          them. They are never sent to AI services, uploaded files are deleted after the
          retention period, and I can delete everything at any time from Settings.
        </span>
      </label>
      {error && (
        <p role="alert" className="text-sm text-bad">
          {error}
        </p>
      )}
      <Button type="submit" disabled={!consent || !name.trim() || busy}>
        {busy ? "Creating…" : "Create profile"}
      </Button>
    </form>
  );
}
