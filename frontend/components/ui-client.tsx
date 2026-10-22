"use client";

import type { ButtonHTMLAttributes } from "react";

export function Button({
  variant = "primary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" }) {
  const styles = {
    primary: "bg-accent text-white hover:opacity-90 dark:text-canvas",
    secondary: "border border-line bg-surface text-ink hover:bg-canvas",
    danger: "border border-bad/40 bg-bad-soft text-bad hover:opacity-90",
  }[variant];
  return (
    <button
      type="button"
      className={`inline-flex items-center justify-center rounded-md px-3.5 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50 ${styles} ${className}`}
      {...props}
    />
  );
}
