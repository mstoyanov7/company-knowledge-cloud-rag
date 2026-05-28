import { Send, X } from "lucide-react";
import { FormEvent, KeyboardEvent, useState } from "react";

type ChatComposerProps = {
  isSubmitting: boolean;
  onSubmit: (question: string) => void;
};

export function ChatComposer({ isSubmitting, onSubmit }: ChatComposerProps) {
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
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
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
        placeholder="Ask a question inside this topic"
        rows={2}
        aria-label="Question"
      />
      {draft ? (
        <button className="composer-clear" type="button" onClick={() => setDraft("")} aria-label="Clear input">
          <X size={16} aria-hidden="true" />
        </button>
      ) : null}
      <button className="composer-send" type="submit" disabled={!draft.trim() || isSubmitting} aria-label="Send">
        <Send size={18} aria-hidden="true" />
      </button>
    </form>
  );
}
