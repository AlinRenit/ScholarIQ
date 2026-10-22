import { plannedPage } from "@/lib/planned";

const { Page, metadata } = plannedPage("/practice", [
  "Topic-linked diagnostic quizzes with locally stored, verified answer keys.",
  "Explanations for every answer and varied questions on retries.",
  "Results recorded as topic evidence that can change a classification.",
]);
export { metadata };
export const dynamic = "force-dynamic";
export default Page;
