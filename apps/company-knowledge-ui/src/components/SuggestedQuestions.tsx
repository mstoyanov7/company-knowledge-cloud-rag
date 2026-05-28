type SuggestedQuestionsProps = {
  questions: string[];
  onSelectQuestion: (question: string) => void;
  compact?: boolean;
};

export function SuggestedQuestions({ questions, onSelectQuestion, compact = false }: SuggestedQuestionsProps) {
  if (questions.length === 0) {
    return null;
  }

  return (
    <section className={compact ? "suggested-questions suggested-questions--compact" : "suggested-questions"}>
      <h3>{compact ? "Try asking" : "Related questions"}</h3>
      <div className="suggested-questions__items">
        {questions.map((question) => (
          <button key={question} type="button" onClick={() => onSelectQuestion(question)}>
            {question}
          </button>
        ))}
      </div>
    </section>
  );
}
