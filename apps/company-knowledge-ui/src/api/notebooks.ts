import { apiRequest } from "./client";

export type NotebookPage = {
  id: string;
  title: string;
  section_path?: string | null;
  source_url: string;
  source_item_id: string;
  source_system: string;
  source_container?: string | null;
  last_modified_utc: string;
  updated_at_utc?: string | null;
  snippet?: string | null;
  last_edited_by?: string | null;
  client_url?: string | null;
  metadata?: Record<string, unknown>;
};

export type NotebookSection = {
  id: string;
  title: string;
  source_url?: string | null;
  section_path?: string | null;
  pages: NotebookPage[];
};

export type Notebook = {
  id: string;
  title: string;
  source_url?: string | null;
  sections: NotebookSection[];
};

export function fetchNotebooks(): Promise<Notebook[]> {
  return apiRequest<Notebook[]>("/api/v1/notebooks");
}

