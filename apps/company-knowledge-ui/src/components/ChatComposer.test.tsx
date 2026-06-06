import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ChatComposer } from "./ChatComposer";

describe("ChatComposer", () => {
  it("shows send when idle and stop while submitting", () => {
    const idle = renderToStaticMarkup(
      <ChatComposer isSubmitting={false} onSubmit={() => undefined} placeholder="Ask" />
    );
    const submitting = renderToStaticMarkup(
      <ChatComposer isSubmitting onSubmit={() => undefined} onStop={() => undefined} placeholder="Ask" />
    );

    expect(idle).toContain('aria-label="Send"');
    expect(idle).not.toContain('aria-label="Stop answer"');
    expect(submitting).toContain('aria-label="Stop answer"');
    expect(submitting).not.toContain('aria-label="Send"');
  });
});
