import { AlertTriangle, Download } from "lucide-react";

import type { Citation, ClarificationOption, DownloadLink } from "../api/answers";
import { downloadApiFile, isApiDownloadUrl } from "../api/client";
import type { ChatMessage as ChatMessageModel } from "../state/conversations";
import { AnswerMeta } from "./AnswerMeta";
import { CitationList } from "./CitationList";
import { ClarificationPrompt } from "./ClarificationPrompt";
import { StreamingAnswer } from "./StreamingAnswer";
import { SuggestedQuestions } from "./SuggestedQuestions";

type ChatMessageProps = {
  message: ChatMessageModel;
  isStreaming?: boolean;
  followUpQuestions?: string[];
  onSelectQuestion: (question: string) => void;
  onOpenSource?: (citation: Citation) => void;
  onStreamTick?: () => void;
  onSelectClarification?: (message: ChatMessageModel, option: ClarificationOption) => void;
};

export function ChatMessage({
  message,
  isStreaming = false,
  followUpQuestions = [],
  onSelectQuestion,
  onOpenSource,
  onStreamTick,
  onSelectClarification
}: ChatMessageProps) {
  const isUser = message.role === "user";
  const citations = message.citations || [];
  const downloads = message.downloads || [];
  const isDone = message.status === "done";
  const hasClarification = !isUser && Boolean(message.clarification?.options?.length);
  const isNoAnswer = !isUser && isDone && citations.length === 0 && !hasClarification;
  const hasLiveContent = !isUser && message.status === "loading" && Boolean(message.content.trim());
  const visibleContent = isDone ? stripTrailingSourceLine(message.content) : message.content;

  if (isUser) {
    return (
      <article className="chat-message chat-message--user">
        <div className="chat-message__content">
          <div className="message-bubble">
            <p>{message.content}</p>
          </div>
        </div>
      </article>
    );
  }

  return (
    <article className="chat-message chat-message--assistant">
      <div className="chat-message__avatar" aria-hidden="true">
        AI
      </div>
      <div className="chat-message__content">
        <div className="bot-name">
          Knowledge Assistant
          {isDone && !isNoAnswer && !hasClarification ? <span className="tag">Grounded answer</span> : null}
          {hasClarification ? <span className="tag">Needs a quick clarification</span> : null}
        </div>

        {hasLiveContent ? (
          <div className="answer-body fade-in">
            <StreamingAnswer answer={message.content} animate={false} onTick={onStreamTick} />
          </div>
        ) : message.status === "loading" ? (
          <div className="message-bubble">
            <div className="typing-state" role="status" aria-label="Searching sources">
              <span />
              <span />
              <span />
            </div>
          </div>
        ) : message.status === "error" ? (
          <p className="message-error">{message.content}</p>
        ) : hasClarification ? (
          <div className="answer-body fade-in">
            <StreamingAnswer answer={visibleContent} animate={false} onTick={onStreamTick} />
            {message.clarification ? (
              <ClarificationPrompt
                clarification={message.clarification}
                resolved={message.clarificationResolved}
                onSelectOption={(option) => onSelectClarification?.(message, option)}
              />
            ) : null}
          </div>
        ) : isNoAnswer ? (
          <div className="statecard statecard--gap fade-in">
            <div className="statecard__icon">
              <AlertTriangle size={20} aria-hidden="true" />
            </div>
            <h3>No grounded answer found</h3>
            <p>{visibleContent || "I could not find anything in the knowledge base that reliably answers that."}</p>
          </div>
        ) : (
          <div className="answer-body fade-in">
            <AnswerMeta citations={citations} />
            <StreamingAnswer answer={visibleContent} animate={false} onTick={onStreamTick} />
            <DownloadList downloads={downloads} />
          </div>
        )}

        {isDone && !isNoAnswer && !hasClarification ? (
          <CitationList citations={citations} onOpenSource={onOpenSource} />
        ) : null}
        {isDone && !hasClarification && followUpQuestions.length ? (
          <SuggestedQuestions questions={followUpQuestions} onSelectQuestion={onSelectQuestion} compact />
        ) : null}
      </div>
    </article>
  );
}

function DownloadList({ downloads }: { downloads: DownloadLink[] }) {
  if (!downloads.length) {
    return null;
  }
  return (
    <div className="download-list" aria-label="Downloads">
      <div className="download-list__title">Downloads</div>
      <ul>
        {downloads.map((download) => (
          <li key={download.download_id}>
            <button
              type="button"
              className="download-link"
              onClick={() => downloadFile(download)}
              aria-label={`Download ${download.file_name}`}
            >
              <Download size={15} aria-hidden="true" />
              <span>
                <strong>{download.file_name}</strong>
                <small>{download.readable ? "Readable source" : "Related file"}</small>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

async function downloadFile(download: DownloadLink): Promise<void> {
  if (isApiDownloadUrl(download.download_url)) {
    await downloadApiFile(download.download_url, download.file_name);
    return;
  }
  window.open(download.download_url, "_blank", "noreferrer");
}

function stripTrailingSourceLine(value: string): string {
  const lines = value.trimEnd().split(/\r?\n/);
  if (!lines.length || !/^\s*[_*]?\s*sources?\s*:\s*.+?\s*[_*]?\s*$/i.test(lines[lines.length - 1])) {
    return value;
  }
  lines.pop();
  while (lines.length && !lines[lines.length - 1].trim()) {
    lines.pop();
  }
  return lines.join("\n");
}
