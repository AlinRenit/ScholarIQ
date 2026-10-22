"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui-client";

export function DeleteMyData() {
  const router = useRouter();
  const [state, setState] = useState<"idle" | "busy" | "done" | "error">("idle");

  async function run() {
    if (
      !window.confirm(
        "Delete your profile, every uploaded file and all academic records? This cannot be undone.",
      )
    )
      return;
    setState("busy");
    const res = await fetch("/api/profile", { method: "DELETE" }).catch(() => null);
    if (res?.status === 204 || res?.status === 401) {
      setState("done");
      // The page re-renders without a profile; the flag keeps the confirmation on screen.
      router.replace("/settings?deleted=1");
      router.refresh();
    } else {
      setState("error");
    }
  }

  if (state === "done") return <p className="text-sm text-ok">All your data has been deleted.</p>;
  return (
    <div className="space-y-2">
      <Button variant="danger" onClick={run} disabled={state === "busy"}>
        {state === "busy" ? "Deleting…" : "Delete my data"}
      </Button>
      {state === "error" && (
        <p role="alert" className="text-sm text-bad">
          Deletion failed. Please try again.
        </p>
      )}
    </div>
  );
}
