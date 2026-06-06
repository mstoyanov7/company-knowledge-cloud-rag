import { HelpCircle } from "lucide-react";

import type { Clarification, ClarificationOption } from "../api/answers";

type ClarificationPromptProps = {
  clarification: Clarification;
  resolved?: boolean;
  onSelectOption: (option: ClarificationOption) => void;
};

export function ClarificationPrompt({ clarification, resolved = false, onSelectOption }: ClarificationPromptProps) {
  return (
    <div className="clarification fade-in" aria-label="Choose a topic">
      <p className="clarification__prompt">
        <HelpCircle size={16} aria-hidden="true" />
        <span>{clarification.prompt}</span>
      </p>
      <ul className="clarification__options">
        {clarification.options.map((option) => (
          <li key={option.source_item_id}>
            <button
              type="button"
              className="clarification__option"
              disabled={resolved}
              onClick={() => onSelectOption(option)}
              aria-label={`Choose ${option.title}`}
            >
              <strong>{option.title}</strong>
              {option.section_path ? <span className="clarification__section">{option.section_path}</span> : null}
              {option.hint ? <span className="clarification__hint">{option.hint}</span> : null}
            </button>
          </li>
        ))}
      </ul>
      {resolved ? <p className="clarification__resolved">Thanks — answering from your choice.</p> : null}
    </div>
  );
}
