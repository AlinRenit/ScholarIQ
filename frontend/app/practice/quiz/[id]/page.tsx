import Link from "next/link";

import { QuizRunner } from "@/components/practice/QuizRunner";
import { Notice, PageHeader } from "@/components/ui";
import type { Quiz } from "@/lib/api";
import { serverGet } from "@/lib/server";

export const dynamic = "force-dynamic";
export const metadata = { title: "Diagnostic quiz" };

export default async function QuizPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const quiz = await serverGet<Quiz>(`/api/practice/quizzes/${encodeURIComponent(id)}`);
  if (!quiz.ok) {
    return (
      <>
        <PageHeader title="Diagnostic quiz" />
        <Notice
          tone={quiz.status === 404 || quiz.status === 401 ? "info" : "error"}
          title={quiz.status === 404 || quiz.status === 401 ? "Quiz not found." : quiz.message}
        >
          <Link href="/practice" className="underline">
            Back to Practice
          </Link>
        </Notice>
      </>
    );
  }
  return (
    <>
      <p className="mb-2 text-sm">
        <Link href="/practice" className="text-ink-muted underline">
          Practice
        </Link>
      </p>
      <PageHeader
        title={`${quiz.data.topic_name}: diagnostic quiz`}
        description="Answer every question, then submit. Each answer is marked against the stored answer key and explained."
      />
      <QuizRunner initial={quiz.data} />
    </>
  );
}
