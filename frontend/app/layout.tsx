import type { Metadata } from "next";
import type { ReactNode } from "react";

import { AppShell } from "@/components/AppShell";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: "ScholarIQ", template: "%s · ScholarIQ" },
  description:
    "Academic performance analysis and personalised tutoring built on deterministic, local algorithms.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="font-sans">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
