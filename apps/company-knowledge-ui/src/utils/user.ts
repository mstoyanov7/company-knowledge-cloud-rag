export function initialsOf(name: string): string {
  return (
    String(name || "")
      .trim()
      .split(/\s+/)
      .slice(0, 2)
      .map((word) => word[0] || "")
      .join("")
      .toUpperCase() || "U"
  );
}

export function firstNameOf(name: string): string {
  return String(name || "").trim().split(/\s+/)[0] || "there";
}

