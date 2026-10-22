import Link from "next/link";

import { StudyPlanView } from "@/components/plan/StudyPlanView";
import { Notice, PageHeader } from "@/components/ui";
import type { CurriculumSubject, Profile, StudyPlan } from "@/lib/api";
import { navItem } from "@/lib/planned";
import { serverGet } from "@/lib/server";

export const dynamic = "force-dynamic";
export const metadata = { title: "Study Plan" };

export default async function StudyPlanPage() {
  const item = navItem("/study-plan");
  const profile = await serverGet<Profile>("/api/profile");
  if (!profile.ok) {
    return (
      <>
        <PageHeader title={item.label} description={item.description} />
        {profile.status === 401 ? (
          <Notice title="Create a profile to get a study plan">
            The plan is built from your results, so it needs a profile. Go to{" "}
            <Link href="/academics" className="underline">
              My Academics
            </Link>{" "}
            to create one and import a marksheet.
          </Notice>
        ) : (
          <Notice tone="error" title="The ScholarIQ API is not reachable.">
            {profile.message}
          </Notice>
        )}
      </>
    );
  }
  const [plan, curriculum] = await Promise.all([
    serverGet<StudyPlan | null>("/api/study-plan"),
    serverGet<CurriculumSubject[]>("/api/curriculum/subjects"),
  ]);
  if (!plan.ok) {
    return (
      <>
        <PageHeader title={item.label} description={item.description} />
        <Notice tone="error" title="Could not load your study plan.">
          {plan.message}
        </Notice>
      </>
    );
  }
  return (
    <>
      <PageHeader title={item.label} description={item.description} />
      <StudyPlanView
        initial={plan.data}
        subjects={curriculum.ok ? curriculum.data.filter((s) => !s.is_custom) : []}
      />
    </>
  );
}
