import {
  ClipboardCheck,
  Download,
  LifeBuoy,
  Rocket,
  Shield,
  Users,
  Wallet,
  Wrench,
  type LucideIcon
} from "lucide-react";

const iconMap: Record<string, LucideIcon> = {
  "clipboard-check": ClipboardCheck,
  download: Download,
  "life-buoy": LifeBuoy,
  rocket: Rocket,
  shield: Shield,
  users: Users,
  wallet: Wallet,
  wrench: Wrench
};

export function getTopicIcon(icon?: string | null): LucideIcon {
  return iconMap[icon ?? ""] || ClipboardCheck;
}
