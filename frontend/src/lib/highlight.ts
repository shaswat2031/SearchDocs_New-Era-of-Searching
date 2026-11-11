export interface TextSegment {
  text: string;
  isMatch: boolean;
  matchIndex: number;
}

export function extractHighlightTerms(query: string): string[] {
  const rawWords = query.match(/[A-Za-z0-9]+/g) || [];
  const terms = rawWords
    .filter((w) => w !== "AND" && w !== "OR" && w !== "NOT")
    .map((w) => w.toLowerCase());
  return Array.from(new Set(terms)).sort((a, b) => b.length - a.length);
}

export function splitHighlightSegments(
  text: string,
  query: string
): TextSegment[] {
  if (!text) return [];
  const terms = extractHighlightTerms(query);
  if (!terms.length) {
    return [{ text, isMatch: false, matchIndex: -1 }];
  }

  const escapedTerms = terms.map((t) =>
    t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
  );
  const regex = new RegExp(`\\b(${escapedTerms.join("|")})\\b`, "gi");

  const segments: TextSegment[] = [];
  let lastIndex = 0;
  let matchIdx = 0;

  let match: RegExpExecArray | null;
  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      segments.push({
        text: text.slice(lastIndex, match.index),
        isMatch: false,
        matchIndex: -1,
      });
    }
    segments.push({
      text: match[0],
      isMatch: true,
      matchIndex: matchIdx,
    });
    matchIdx += 1;
    lastIndex = match.index + match[0].length;
    if (match[0].length === 0) {
      regex.lastIndex += 1;
    }
  }

  if (lastIndex < text.length) {
    segments.push({
      text: text.slice(lastIndex),
      isMatch: false,
      matchIndex: -1,
    });
  }

  return segments;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

