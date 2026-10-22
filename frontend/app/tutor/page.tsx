import { plannedPage } from "@/lib/planned";

const { Page, metadata } = plannedPage("/tutor", [
  "Understand definition, comparison, procedure, prerequisite and practice questions.",
  "Retrieve verified material with BM25 and answer with specialised deterministic handlers.",
  "Adjust teaching depth to your topic evidence without changing the facts.",
  "Cite sources, and say so plainly when the knowledge base cannot answer.",
]);
export { metadata };
export const dynamic = "force-dynamic";
export default Page;
