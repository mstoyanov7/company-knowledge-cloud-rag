import { useEffect, useRef, useState } from "react";

import { MarkdownAnswer } from "./MarkdownAnswer";

type StreamingAnswerProps = {
  answer: string;
  /** Animate a progressive reveal of the (already-fetched) answer. */
  animate: boolean;
  onTick?: () => void;
};

// Tracks which message renders have already played their reveal so reopening a
// conversation doesn't replay the animation. Keyed by answer content identity
// is not reliable, so the parent only sets `animate` for the just-completed one.
const WORDS_PER_TICK = 4;
const TICK_MS = 28;

export function StreamingAnswer({ answer, animate, onTick }: StreamingAnswerProps) {
  const words = answer.split(/(\s+)/);
  const [revealed, setRevealed] = useState(animate ? 0 : words.length);
  const doneRef = useRef(!animate);

  useEffect(() => {
    if (!animate || doneRef.current) {
      return undefined;
    }
    let count = 0;
    const id = window.setInterval(() => {
      count += WORDS_PER_TICK;
      if (count >= words.length) {
        doneRef.current = true;
        setRevealed(words.length);
        window.clearInterval(id);
      } else {
        setRevealed(count);
      }
      onTick?.();
    }, TICK_MS);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [animate]);

  if (revealed >= words.length) {
    return <MarkdownAnswer answer={answer} />;
  }

  return (
    <div className="markdown-answer streaming">
      <p>
        {words.slice(0, revealed).join("")}
        <span className="caret" aria-hidden="true" />
      </p>
    </div>
  );
}
