import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type MarkdownAnswerProps = {
  answer: string;
};

export function MarkdownAnswer({ answer }: MarkdownAnswerProps) {
  return (
    <div className="markdown-answer">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{answer}</ReactMarkdown>
    </div>
  );
}
