const SAFE_METHODS = new Set(["GET", "HEAD"]);

/**
 * Refuse state-changing requests sent by another site. The session cookie is
 * SameSite=Lax already; this is a second check that does not depend on the
 * browser honouring that attribute.
 */
export function crossSite(req: Request): boolean {
  if (SAFE_METHODS.has(req.method)) return false;
  const origin = req.headers.get("origin");
  if (origin) {
    const host = req.headers.get("x-forwarded-host") ?? req.headers.get("host");
    try {
      return new URL(origin).host !== host;
    } catch {
      return true;
    }
  }
  return req.headers.get("sec-fetch-site") === "cross-site";
}
