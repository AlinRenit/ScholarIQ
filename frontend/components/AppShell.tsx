"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";

import { NAV_ITEMS, isActive } from "@/lib/nav";

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? "/";
  const [open, setOpen] = useState(false);

  const nav = (
    <nav aria-label="Main">
      <ul className="space-y-0.5">
        {NAV_ITEMS.map((item) => {
          const active = isActive(pathname, item.href);
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                aria-current={active ? "page" : undefined}
                onClick={() => setOpen(false)}
                className={`block rounded-md px-3 py-2 text-sm transition-colors ${
                  active
                    ? "bg-accent-soft font-medium text-accent"
                    : "text-ink-muted hover:bg-canvas hover:text-ink"
                }`}
              >
                {item.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[15rem_1fr]">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-surface focus:px-3 focus:py-2"
      >
        Skip to content
      </a>

      <aside className="hidden border-r border-line bg-surface px-4 py-6 lg:block">
        <Brand />
        <div className="mt-8">{nav}</div>
        <p className="mt-10 px-3 text-xs leading-relaxed text-ink-subtle">
          All analysis and answers are computed locally. No language models or external AI services
          are used.
        </p>
      </aside>

      <header className="flex items-center justify-between border-b border-line bg-surface px-4 py-3 lg:hidden">
        <Brand />
        <button
          type="button"
          aria-expanded={open}
          aria-controls="mobile-nav"
          onClick={() => setOpen((v) => !v)}
          className="rounded-md border border-line px-3 py-1.5 text-sm"
        >
          {open ? "Close" : "Menu"}
        </button>
      </header>
      {open && (
        <div id="mobile-nav" className="border-b border-line bg-surface px-4 py-3 lg:hidden">
          {nav}
        </div>
      )}

      <main id="main" className="mx-auto w-full max-w-5xl px-4 py-8 sm:px-8 lg:py-12">
        {children}
      </main>
    </div>
  );
}

function Brand() {
  return (
    <Link href="/" className="flex items-baseline gap-2 px-3">
      <span className="text-lg font-semibold tracking-tight">ScholarIQ</span>
      <span className="text-xs text-ink-subtle">AI-free</span>
    </Link>
  );
}
