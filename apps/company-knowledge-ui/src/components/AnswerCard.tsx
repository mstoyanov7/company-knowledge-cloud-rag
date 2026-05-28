import type { AnswerResponse } from "../api/answers";
import { CitationList } from "./CitationList";
import { ErrorState } from "./ErrorState";
import { MarkdownAnswer } from "./MarkdownAnswer";
import { SuggestedQuestions } from "./SuggestedQuestions";

type AnswerCardProps = {
  question: string;
  response?: AnswerResponse;
  error?: string;
  isPending?: boolean;
  fallbackSuggestions: string[];
  onSelectQuestion: (question: string) => void;
};

export function AnswerCard({
  question,
  response,
  error,
  isPending = false,
  fallbackSuggestions,
  onSelectQuestion
}: AnswerCardProps) {
  const suggestions = response?.suggested_questions?.length ? response.suggested_questions : fallbackSuggestions;

  return (
    <article className="answer-card">
      <div className="answer-card__header">
        <span className="answer-card__label">Question</span>
        <h2>{question}</h2>
      </div>
      {isPending ? <div className="inline-loading" role="status">Preparing answer</div> : null}
      {error ? <ErrorState title="Answer unavailable" message={error} /> : null}
      {response ? (
        <>
          <MarkdownAnswer answer={response.answer} />
          <CitationList citations={response.citations} />
          <SuggestedQuestions questions={suggestions} onSelectQuestion={onSelectQuestion} />
        </>
      ) : null}
    </article>
  );
}
