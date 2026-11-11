export interface StatsResponse {
  total_documents: number;
  vocabulary_size: number;
  total_tokens: number;
  avg_doc_length: number;
  parallel_active: boolean;
  parallel_workers: number;
}

export interface DocumentResponse {
  doc_id: number;
  external_id: string | null;
  title: string;
  content: string;
  doc_length: number;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface SearchHitResponse {
  doc_id: number;
  external_id: string | null;
  title: string;
  score: number;
  snippet: string;
  match_count: number;
  snippets: string[];
  content: string | null;
  metadata: Record<string, unknown>;
}

export interface SearchApiResponse {
  query: string;
  total_hits: number;
  took_ms: number;
  mode: "serial" | "parallel";
  hits: SearchHitResponse[];
}

export interface SearchParams {
  q: string;
  limit: number;
  offset: number;
  operator: "AND" | "OR";
  include_content?: boolean;
  parallel: boolean;
}

export interface RebuildResponse {
  documents_reindexed: number;
  vocabulary_size: number;
  total_tokens?: number;
}

export interface ImportDirectoryResponse {
  imported_count: number;
  doc_ids: number[];
}

export function getApiBase(): string {
  if (process.env.NEXT_PUBLIC_API_BASE) {
    return process.env.NEXT_PUBLIC_API_BASE.replace(/\/$/, "");
  }
  if (
    typeof window !== "undefined" &&
    (window.location.port === "3000" || window.location.port === "3001")
  ) {
    return "http://127.0.0.1:8000";
  }
  return "";
}

async function requestJson<T>(path: string, options: RequestInit = {}): Promise<T> {
  const url = `${getApiBase()}${path}`;
  const isFormData =
    typeof FormData !== "undefined" && options.body instanceof FormData;

  const headers: Record<string, string> = isFormData
    ? {}
    : { "Content-Type": "application/json" };

  if (options.headers) {
    Object.assign(headers, options.headers as Record<string, string>);
  }

  const res = await fetch(url, {
    ...options,
    headers,
  });

  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail =
      typeof body?.detail === "string"
        ? body.detail
        : `Request failed (${res.status})`;
    throw new Error(detail);
  }
  return body as T;
}

export async function fetchStats(): Promise<StatsResponse> {
  return requestJson<StatsResponse>("/stats");
}

export async function searchDocuments(
  params: SearchParams
): Promise<SearchApiResponse> {
  return requestJson<SearchApiResponse>("/search", {
    method: "POST",
    body: JSON.stringify({
      q: params.q,
      limit: params.limit,
      offset: params.offset,
      operator: params.operator,
      include_content: params.include_content ?? true,
      parallel: params.parallel,
    }),
  });
}

export async function uploadFiles(files: File[]): Promise<DocumentResponse[]> {
  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file, file.name);
  }
  return requestJson<DocumentResponse[]>("/documents/upload", {
    method: "POST",
    body: formData,
  });
}

export async function importDirectory(
  directory: string
): Promise<ImportDirectoryResponse> {
  return requestJson<ImportDirectoryResponse>("/documents/import-directory", {
    method: "POST",
    body: JSON.stringify({ directory }),
  });
}

export async function listDocuments(
  limit = 200,
  offset = 0
): Promise<DocumentResponse[]> {
  return requestJson<DocumentResponse[]>(
    `/documents?limit=${limit}&offset=${offset}`
  );
}

export async function getDocument(docId: number): Promise<DocumentResponse> {
  return requestJson<DocumentResponse>(`/documents/${docId}`);
}

export async function createDocument(payload: {
  title: string;
  content: string;
  external_id: string | null;
  metadata: Record<string, unknown>;
}): Promise<DocumentResponse> {
  return requestJson<DocumentResponse>("/documents", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateDocument(
  docId: number,
  payload: {
    title: string;
    content: string;
    metadata: Record<string, unknown>;
  }
): Promise<DocumentResponse> {
  return requestJson<DocumentResponse>(`/documents/${docId}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function deleteDocument(docId: number): Promise<void> {
  await requestJson<unknown>(`/documents/${docId}`, {
    method: "DELETE",
  });
}

export async function rebuildIndex(): Promise<RebuildResponse> {
  return requestJson<RebuildResponse>("/index/rebuild", {
    method: "POST",
  });
}
