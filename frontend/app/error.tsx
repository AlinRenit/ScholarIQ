"use client";

import { Notice } from "@/components/ui";

export default function ErrorPage({ reset }: { error: Error; reset: () => void }) {
  return (
    <Notice tone="error" title="Something went wrong while loading this page.">
      <button type="button" onClick={reset} className="mt-2 underline">
        Try again
      </button>
    </Notice>
  );
}
