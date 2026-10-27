// Answers mark where each fact comes from with [1], [2], ...: [n] cites sources[n - 1].
// A "[n](...)" is a Markdown link, not a citation.
const CITATION = /\[(\d+)\](?!\()/g;

export function hasCitations(text: string): boolean {
  return new RegExp(CITATION.source).test(text);
}

// For previews and earlier turns, where the numbers have no sources to open.
export function stripCitations(text: string): string {
  return text.replace(CITATION, "");
}

// Citations become links so Markdown keeps them inline, in lists and bold text alike.
export function linkCitations(text: string, typing: boolean): string {
  // While the answer types out, a half-written "[1" would flash up as text.
  const shown = typing ? text.replace(/\[\d*$/, "") : text;
  return shown.replace(CITATION, (_, number: string) => `[${number}](#source-${number})`);
}
