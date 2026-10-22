/**
 * Split stored text into paragraphs and undo its hard line wraps. In worked
 * examples a line that ends a sentence keeps its break, because each line is
 * usually a step.
 */
export function paragraphs(body: string, keepSentenceLines: boolean): string[] {
  const wrap = keepSentenceLines ? /(?<![.:;!?])[ \t]*\n[ \t]*/g : /[ \t]*\n[ \t]*/g;
  return body
    .split(/\n\s*\n/)
    .map((p) => p.trim().replace(wrap, " "))
    .filter(Boolean);
}
