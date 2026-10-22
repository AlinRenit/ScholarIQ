import { plannedPage } from "@/lib/planned";

const { Page, metadata } = plannedPage("/academics", [
  "Upload PDF, scanned, image, CSV and XLSX marksheets.",
  "Extract subjects, marks, maximum marks, grades, credits and semesters with local parsers and Tesseract OCR.",
  "Review and correct every extracted value before anything is saved.",
  "Ask you to map unfamiliar grade scales instead of guessing them.",
]);
export { metadata };
export const dynamic = "force-dynamic";
export default Page;
