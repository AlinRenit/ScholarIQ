import Link from "next/link";

import { TutorWorkspace } from "@/components/tutor/TutorWorkspace";
import { Notice, PageHeader } from "@/components/ui";
import type { ConversationSummary, Profile, TutorInfo } from "@/lib/api";
import { navItem } from "@/lib/planned";
import { serverGet } from "@/lib/server";

export const dynamic = "force-dynamic";
export const metadata = { title: "AI-Free Tutor" };

export default async function TutorPage() {
  const item = navItem("/tutor");
  const profile = await serverGet<Profile>("/api/profile");
  if (!profile.ok) {
    return (
      <>
        <PageHeader title={item.label} description={item.description} />
        {profile.status === 401 ? (
          <Notice title="Create a profile to use the tutor">
            Go to{" "}
            <Link href="/academics" className="underline">
              My Academics
            </Link>{" "}
            to create a local profile. The tutor needs one so it can keep your conversations private
            and match its depth to your topic results. You can browse the{" "}
            <Link href="/knowledge-base" className="underline">
              knowledge base
            </Link>{" "}
            without one.
          </Notice>
        ) : (
          <Notice tone="error" title="The ScholarIQ API is not reachable.">
            {profile.message}
          </Notice>
        )}
      </>
    );
  }

  const [conversations, info] = await Promise.all([
    serverGet<ConversationSummary[]>("/api/tutor/conversations"),
    serverGet<TutorInfo>("/api/tutor/info"),
  ]);
  return (
    <>
      <PageHeader title={item.label} description={item.description} />
      {!conversations.ok && (
        <div className="mb-4">
          <Notice tone="error" title="Could not load your saved conversations.">
            {conversations.message} You can still ask new questions.
          </Notice>
        </div>
      )}
      <TutorWorkspace
        initialConversations={conversations.ok ? conversations.data : []}
        info={info.ok ? info.data : null}
      />
    </>
  );
}
