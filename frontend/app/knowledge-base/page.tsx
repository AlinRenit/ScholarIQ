import { plannedPage } from "@/lib/planned";

const { Page, metadata } = plannedPage("/knowledge-base", [
  "Browse courses, subjects, topics, concepts, examples and exercises.",
  "Import Markdown, YAML, JSON, text and PDF material, reviewed before it is trusted.",
  "Track versions, provenance and licensing for every item.",
]);
export { metadata };
export const dynamic = "force-dynamic";
export default Page;
