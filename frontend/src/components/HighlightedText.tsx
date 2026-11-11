"use client";

import React, { useMemo } from "react";
import { splitHighlightSegments } from "@/lib/highlight";

interface HighlightedTextProps {
  text: string;
  query: string;
  activeMatchIndex?: number;
  markRefs?: React.MutableRefObject<(HTMLElement | null)[]>;
}

export function HighlightedText({
  text,
  query,
  activeMatchIndex = -1,
  markRefs,
}: HighlightedTextProps) {
  const segments = useMemo(
    () => splitHighlightSegments(text, query),
    [text, query]
  );

  return (
    <>
      {segments.map((seg, idx) =>
        seg.isMatch ? (
          <mark
            key={`${idx}-${seg.matchIndex}`}
            ref={(el) => {
              if (markRefs) {
                markRefs.current[seg.matchIndex] = el;
              }
            }}
            className={
              seg.matchIndex === activeMatchIndex
                ? "sc-mark sc-mark-active"
                : "sc-mark"
            }
          >
            {seg.text}
          </mark>
        ) : (
          <React.Fragment key={idx}>{seg.text}</React.Fragment>
        )
      )}
    </>
  );
}

