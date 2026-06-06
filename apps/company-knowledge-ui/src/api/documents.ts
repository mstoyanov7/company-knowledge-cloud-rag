import { apiRequest } from "./client";
import type { NotebookPage } from "./notebooks";

export type DocumentSummary = NotebookPage;

export type DocumentDetail = DocumentSummary & {
  content_text: string;
};

export function fetchRecentlyUpdatedDocuments(limit = 8): Promise<DocumentSummary[]> {
  return apiRequest<DocumentSummary[]>(`/api/v1/documents?sort=recently_updated&limit=${limit}`);
}

export function fetchDocumentDetail(sourceItemId: string, sourceSystem?: string): Promise<DocumentDetail> {
  const params = new URLSearchParams({ source_item_id: sourceItemId });
  if (sourceSystem) {
    params.set("source_system", sourceSystem);
  }
  return apiRequest<DocumentDetail>(`/api/v1/documents/detail?${params.toString()}`);
}

