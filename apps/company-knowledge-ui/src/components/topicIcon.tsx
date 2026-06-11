import {
  BadgeHelp,
  BookOpen,
  CircleHelp,
  ClipboardCheck,
  Download,
  FolderKanban,
  Gift,
  GraduationCap,
  KeyRound,
  Layers,
  LifeBuoy,
  NotebookTabs,
  Rocket,
  Shield,
  ShieldCheck,
  Users,
  UsersRound,
  Wallet,
  WalletCards,
  Wrench,
  type LucideIcon
} from "lucide-react";

export type TopicIconOption = {
  id: string;
  label: string;
  Icon: LucideIcon;
};

export const TOPIC_ICON_OPTIONS: TopicIconOption[] = [
  { id: "badge-help", label: "Help badge", Icon: BadgeHelp },
  { id: "book-open", label: "Handbook", Icon: BookOpen },
  { id: "circle-help", label: "Question", Icon: CircleHelp },
  { id: "clipboard-check", label: "Checklist", Icon: ClipboardCheck },
  { id: "download", label: "Download", Icon: Download },
  { id: "folder-kanban", label: "Projects", Icon: FolderKanban },
  { id: "gift", label: "Benefits", Icon: Gift },
  { id: "graduation-cap", label: "Onboarding", Icon: GraduationCap },
  { id: "key-round", label: "Access", Icon: KeyRound },
  { id: "layers", label: "Layers", Icon: Layers },
  { id: "life-buoy", label: "Support", Icon: LifeBuoy },
  { id: "notebook-tabs", label: "Notebook", Icon: NotebookTabs },
  { id: "rocket", label: "Release", Icon: Rocket },
  { id: "shield", label: "Security", Icon: Shield },
  { id: "shield-check", label: "Compliance", Icon: ShieldCheck },
  { id: "users", label: "Users", Icon: Users },
  { id: "users-round", label: "People", Icon: UsersRound },
  { id: "wallet", label: "Finance", Icon: Wallet },
  { id: "wallet-cards", label: "Procurement", Icon: WalletCards },
  { id: "wrench", label: "Tools", Icon: Wrench }
];

const iconMap = TOPIC_ICON_OPTIONS.reduce<Record<string, LucideIcon>>((map, option) => {
  map[option.id] = option.Icon;
  return map;
}, {});

export function getTopicIcon(icon?: string | null): LucideIcon {
  return iconMap[icon ?? ""] || NotebookTabs;
}
