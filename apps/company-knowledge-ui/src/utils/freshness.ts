const MS_PER_DAY = 1000 * 60 * 60 * 24;
const MS_PER_HOUR = 1000 * 60 * 60;
const MS_PER_MINUTE = 1000 * 60;

// Sources older than this are flagged with a "verify" warning.
const STALE_DAYS = 365;

function ageInDays(value: string): number | null {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  return Math.max(0, (Date.now() - date.getTime()) / MS_PER_DAY);
}

export function formatRelativeAge(value: string): string {
  const days = ageInDays(value);
  if (days === null) {
    return value;
  }
  if (days < 1) {
    return "today";
  }
  if (days < 14) {
    const whole = Math.round(days);
    return `${whole} day${whole === 1 ? "" : "s"} ago`;
  }
  if (days < 60) {
    const weeks = Math.round(days / 7);
    return `${weeks} week${weeks === 1 ? "" : "s"} ago`;
  }
  if (days < 365) {
    const months = Math.round(days / 30);
    return `${months} month${months === 1 ? "" : "s"} ago`;
  }
  const years = Math.round(days / 365);
  return `${years} year${years === 1 ? "" : "s"} ago`;
}

export function formatUpdateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  const now = new Date();
  if (sameLocalDate(date, now)) {
    const deltaMs = Math.max(0, now.getTime() - date.getTime());
    if (deltaMs < MS_PER_MINUTE) {
      const seconds = Math.max(1, Math.floor(deltaMs / 1000));
      return `${seconds} second${seconds === 1 ? "" : "s"} ago`;
    }
    if (deltaMs < MS_PER_HOUR) {
      const minutes = Math.floor(deltaMs / MS_PER_MINUTE);
      return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
    }
    const hours = Math.floor(deltaMs / MS_PER_HOUR);
    return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  }
  return `${pad2(date.getDate())}.${pad2(date.getMonth() + 1)}`;
}

export function isStale(value: string): boolean {
  const days = ageInDays(value);
  return days !== null && days > STALE_DAYS;
}

function sameLocalDate(left: Date, right: Date): boolean {
  return (
    left.getFullYear() === right.getFullYear() &&
    left.getMonth() === right.getMonth() &&
    left.getDate() === right.getDate()
  );
}

function pad2(value: number): string {
  return value.toString().padStart(2, "0");
}
