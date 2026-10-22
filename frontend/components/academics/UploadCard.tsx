"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState, type DragEvent } from "react";

import { Button } from "@/components/ui-client";
import { errorMessage } from "@/lib/api";

const ACCEPT = ".pdf,.png,.jpg,.jpeg,.xlsx,.csv,.txt";

export function UploadCard({ maxMb }: { maxMb: number }) {
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [existing, setExisting] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  async function send(file: File) {
    setBusy(true);
    setError(null);
    setExisting(null);
    const form = new FormData();
    form.append("file", file);
    const res = await fetch("/api/documents", { method: "POST", body: form }).catch(() => null);
    const body: unknown = await res?.json().catch(() => null);
    setBusy(false);
    if (res?.status === 201 && body && typeof body === "object" && "id" in body) {
      router.push(`/academics/import/${String(body.id)}`);
      return;
    }
    if (res?.status === 409 && body && typeof body === "object" && "detail" in body) {
      const detail = body.detail as { document_id?: string };
      setExisting(detail.document_id ?? null);
    }
    setError(errorMessage(body, "The upload failed. Please try again."));
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) void send(file);
  }

  return (
    <section
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      className={`rounded-lg border border-dashed p-6 text-center transition ${
        dragging ? "border-accent bg-accent-soft" : "border-line bg-surface"
      }`}
    >
      <h2 className="font-semibold">Import a marksheet</h2>
      <p className="mx-auto mt-1 max-w-md text-sm text-ink-muted">
        PDF (digital or scanned), PNG, JPEG, XLSX, CSV or TXT, up to {maxMb} MB. You will review
        every extracted value before anything is saved.
      </p>
      <input
        ref={input}
        type="file"
        accept={ACCEPT}
        className="sr-only"
        aria-label="Choose a marksheet file"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) void send(file);
          e.target.value = "";
        }}
      />
      <Button className="mt-4" disabled={busy} onClick={() => input.current?.click()}>
        {busy ? "Reading file…" : "Choose file"}
      </Button>
      <p className="mt-2 text-xs text-ink-subtle">or drop it here</p>
      {error && (
        <p role="alert" className="mt-3 text-sm text-bad">
          {error}{" "}
          {existing && (
            <Link className="underline" href={`/academics/import/${existing}`}>
              Open the earlier upload
            </Link>
          )}
        </p>
      )}
    </section>
  );
}
