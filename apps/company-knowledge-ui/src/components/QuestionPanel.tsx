import { Send } from "lucide-react";
import { FormEvent, KeyboardEvent, useState } from "react";

type QuestionPanelProps = {
  initialQuestion?: string;
  isSubmitting: boolean;
  onSubmit: (question: string) => void;
};

export function QuestionPanel({ initialQuestion = "", isSubmitting, onSubmit }: QuestionPanelProps) {
  const [question, setQuestion] = useState(initialQuestion);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    submitQuestion();
  }

  function submitQuestion() {
    const trimmedQuestion = question.trim();
    if (!trimmedQuestion || isSubmitting) {
      return;
    }
    onSubmit(trimmedQuestion);
    setQuestion("");
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      submitQuestion();
    }
  }

  return (
    <form className="question-panel" onSubmit={handleSubmit}>
      <label className="field-label" htmlFor="knowledge-question">
        Question
      </label>
      <div className="question-panel__row">
        <textarea
          id="knowledge-question"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask a specific question inside this topic"
          rows={3}
        />
        <button className="primary-action" type="submit" disabled={!question.trim() || isSubmitting}>
          <Send size={18} aria-hidden="true" />
          <span>{isSubmitting ? "Asking" : "Ask"}</span>
        </button>
      </div>
    </form>
  );
}
