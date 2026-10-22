import { plannedPage } from "@/lib/planned";

const { Page, metadata } = plannedPage("/study-plan", [
  "Order topics by a published priority formula using weakness, importance and prerequisites.",
  "Show each term of the score so the ranking can be checked.",
  "Track completed lessons separately from demonstrated mastery.",
]);
export { metadata };
export const dynamic = "force-dynamic";
export default Page;
