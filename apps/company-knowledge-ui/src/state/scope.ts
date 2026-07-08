// Per-user scoping for browser-persisted state (conversations, pins). Without
// this, every user on the same browser shares the same localStorage key, so one
// user's chat history leaks to the next. The active user's id is appended to the
// base key so each account keeps its own isolated history.
let scopeSuffix = "";

export function setUserScope(userId: string | null | undefined): void {
  scopeSuffix = userId ? `.${userId}` : "";
}

export function scopedKey(baseKey: string): string {
  return `${baseKey}${scopeSuffix}`;
}
