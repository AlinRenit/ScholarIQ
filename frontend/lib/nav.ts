export type NavItem = {
  href: string;
  label: string;
  description: string;
  /** Key in the backend capability list that must be available for the page to work. */
  capability: string;
};

export const NAV_ITEMS: readonly NavItem[] = [
  {
    href: "/",
    label: "Dashboard",
    description: "Your academic overview, topic evidence and next steps.",
    capability: "analytics",
  },
  {
    href: "/academics",
    label: "My Academics",
    description: "Upload marksheets, review extracted results and see subject performance.",
    capability: "marksheet_import",
  },
  {
    href: "/topics",
    label: "Topics",
    description: "Topics mapped from your subjects, with the evidence behind each classification.",
    capability: "analytics",
  },
  {
    href: "/tutor",
    label: "AI-Free Tutor",
    description:
      "Ask academic questions. Answers come from a curated local knowledge base and deterministic handlers, never a language model.",
    capability: "tutor",
  },
  {
    href: "/practice",
    label: "Practice",
    description:
      "Diagnostic quizzes on each topic. Results become topic evidence and can change a classification.",
    capability: "diagnostics",
  },
  {
    href: "/study-plan",
    label: "Study Plan",
    description: "A prerequisite-aware study sequence with a transparent priority score.",
    capability: "diagnostics",
  },
  {
    href: "/knowledge-base",
    label: "Knowledge Base",
    description: "Browse and administer the versioned concept library and its sources.",
    capability: "knowledge_base",
  },
  {
    href: "/settings",
    label: "Settings",
    description: "System status, privacy information and data deletion.",
    capability: "foundation",
  },
];

export function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}
