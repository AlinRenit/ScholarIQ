import { PlannedFeature } from "@/components/PlannedFeature";
import { api, load } from "@/lib/api";
import { NAV_ITEMS } from "@/lib/nav";

export function navItem(href: string) {
  const item = NAV_ITEMS.find((n) => n.href === href);
  if (!item) throw new Error(`No navigation item for ${href}`);
  return item;
}

/** Build a server page for a section that is planned but not implemented. */
export function plannedPage(href: string, plannedScope: string[]) {
  const item = navItem(href);
  async function Page() {
    const info = await load(() => api.systemInfo());
    const capability = info.data?.capabilities.find((c) => c.key === item.capability);
    return <PlannedFeature item={item} capability={capability} plannedScope={plannedScope} />;
  }
  return { Page, metadata: { title: item.label } };
}
