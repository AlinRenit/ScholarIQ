import { plannedPage } from "@/lib/planned";

const { Page, metadata } = plannedPage("/topics", [
  "Map each subject to its topics using a configurable curriculum.",
  "Classify topics as Strong, Developing, Needs attention or Insufficient evidence.",
  "Show the evidence behind each classification. Subject marks count only as a weak prior.",
]);
export { metadata };
export const dynamic = "force-dynamic";
export default Page;
