import { Send, Square, X } from "lucide-react";
import { FormEvent, KeyboardEvent, useState } from "react";

type ChatComposerProps = {
  isSubmitting: boolean;
  onSubmit: (question: string) => void;
  onStop?: () => void;
  placeholder?: string;
};

export function ChatComposer({ isSubmitting, onSubmit, onStop, placeholder }: ChatComposerProps) {
  const [draft, setDraft] = useState("");

  function submitDraft() {
    const question = draft.trim();
    if (!question || isSubmitting) {
      return;
    }
    onSubmit(question);
    setDraft("");
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    submitDraft();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submitDraft();
      return;
    }

    if (event.key === "Escape" && draft) {
      event.preventDefault();
      setDraft("");
    }
  }

  return (
    <form className="chat-composer" onSubmit={handleSubmit}>
      <textarea
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder || "Ask a question inside this topic"}
        rows={1}
        aria-label="Question"
      />
      {draft ? (
        <button className="composer-clear" type="button" onClick={() => setDraft("")} aria-label="Clear input">
          <X size={16} aria-hidden="true" />
        </button>
      ) : null}
      {isSubmitting ? (
        <button className="composer-send composer-stop" type="button" onClick={onStop} aria-label="Stop answer">
          <Square size={15} aria-hidden="true" />
        </button>
      ) : (
        <button className="composer-send" type="submit" disabled={!draft.trim()} aria-label="Send">
          <Send size={18} aria-hidden="true" />
        </button>
      )}
    </form>
  );
}
