import { Check, Copy } from "lucide-react";
import { Children, isValidElement, useState, type ComponentPropsWithoutRef, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { downloadApiFile, isApiDownloadUrl } from "../api/client";

type MarkdownAnswerProps = {
  answer: string;
};

export function MarkdownAnswer({ answer }: MarkdownAnswerProps) {
  return (
    <div className="markdown-answer">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          pre({ children }: ComponentPropsWithoutRef<"pre">) {
            const child = Children.toArray(children)[0];
            if (isValidElement<CodeElementProps>(child)) {
              const language = /language-([^\s]+)/.exec(child.props.className || "")?.[1] || "text";
              const code = String(child.props.children ?? "").replace(/\n$/, "");
              return <CopyableCodeBlock code={code} language={language} />;
            }
            return <pre>{children}</pre>;
          },
          code({ className, children }: ComponentPropsWithoutRef<"code">) {
            return <code className={className}>{children}</code>;
          },
          a({ href, children, ...props }: ComponentPropsWithoutRef<"a">) {
            return (
              <a
                {...props}
                href={href}
                onClick={(event) => {
                  if (!href || !isApiDownloadUrl(href)) {
                    return;
                  }
                  event.preventDefault();
                  void downloadApiFile(href, textFromChildren(children));
                }}
              >
                {children}
              </a>
            );
          }
        }}
      >
        {answer}
      </ReactMarkdown>
    </div>
  );
}

function textFromChildren(children: ReactNode): string {
  if (typeof children === "string") {
    return children;
  }
  if (Array.isArray(children)) {
    return children.map(textFromChildren).join("");
  }
  return "download";
}

type CodeElementProps = {
  className?: string;
  children?: ReactNode;
};

type CopyableCodeBlockProps = {
  code: string;
  language: string;
};

function CopyableCodeBlock({ code, language }: CopyableCodeBlockProps) {
  const [copied, setCopied] = useState(false);

  async function copyCode() {
    await copyText(code);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  }

  return (
    <div className="codeblock">
      <div className="codeblock__bar">
        <span className="codeblock__lang">{language}</span>
        <button className="codeblock__copy" type="button" onClick={copyCode} aria-label="Copy code">
          {copied ? <Check size={13} aria-hidden="true" /> : <Copy size={13} aria-hidden="true" />}
          <span>{copied ? "Copied" : "Copy"}</span>
        </button>
      </div>
      <pre>
        <code className={`language-${language}`}>{code}</code>
      </pre>
    </div>
  );
}

async function copyText(value: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }
  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand("copy");
  document.body.removeChild(textarea);
}
