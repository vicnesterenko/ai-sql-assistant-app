export const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000';

export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH';

export type AssistantResponse = {
  message: string;
  sql?: string | null;
  risk_level?: RiskLevel | null;
  risk_justification?: string | null;
  assumptions: string[];
  columns: string[];
  rows: Record<string, unknown>[];
  truncated: boolean;
  pending_approval: boolean;
  approval_request_id?: string | null;
  rejection_reason?: string | null;
  audit_id?: string | null;
  execution_status?: string | null;
};

export type MessageRecord = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
  response?: AssistantResponse | null;
};

export type ApprovalItem = {
  id: string;
  session_id: string;
  thread_id: string;
  requester_email: string;
  original_question: string;
  generated_sql: string;
  risk_level: string;
  risk_justification: string;
  status: string;
  approver_email?: string | null;
  approved_sql?: string | null;
  rejection_reason?: string | null;
  created_at: string;
  resolved_at?: string | null;
};

export type AuditEntry = {
  id: string;
  session_id: string;
  question: string;
  generated_sql?: string | null;
  final_sql?: string | null;
  risk_level?: string | null;
  execution_status?: string | null;
  execution_duration_ms?: number | null;
  row_count?: number | null;
  error_message?: string | null;
  created_at: string;
};

export type SchemaTable = {
  name: string;
  description: string;
  large: boolean;
  sensitive: boolean;
  columns: { name: string; data_type: string; nullable: boolean; description?: string | null }[];
};

function headers(role: string, email: string): HeadersInit {
  return {
    'Content-Type': 'application/json',
    'X-User-Email': email,
    'X-User-Role': role,
  };
}

export async function createSession(email: string, role: string) {
  const res = await fetch(`${API_BASE}/api/sessions`, {
    method: 'POST',
    headers: headers(role, email),
    body: JSON.stringify({ requester_email: email }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<{ session_id: string; created_at: string }>;
}

export async function sendMessage(sessionId: string, message: string, email: string, role: string) {
  const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/messages`, {
    method: 'POST',
    headers: headers(role, email),
    body: JSON.stringify({ message, thread_id: 'default' }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<{ response: AssistantResponse }>;
}

export async function getMessages(sessionId: string, email: string, role: string) {
  const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/messages`, { headers: headers(role, email) });
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<{ messages: MessageRecord[] }>;
}

export async function listApprovals(email: string, role: string) {
  const res = await fetch(`${API_BASE}/api/approvals?status=pending`, { headers: headers(role, email) });
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<{ items: ApprovalItem[]; total: number }>;
}

export async function getApproval(id: string, email: string, role: string) {
  const res = await fetch(`${API_BASE}/api/approvals/${id}`, { headers: headers(role, email) });
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<ApprovalItem>;
}

export async function approveQuery(id: string, modified_sql: string | null, email: string, role: string) {
  const res = await fetch(`${API_BASE}/api/approvals/${id}/approve`, {
    method: 'POST',
    headers: headers(role, email),
    body: JSON.stringify({ modified_sql }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function rejectQuery(id: string, reason: string, email: string, role: string) {
  const res = await fetch(`${API_BASE}/api/approvals/${id}/reject`, {
    method: 'POST',
    headers: headers(role, email),
    body: JSON.stringify({ reason }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function listHistory(sessionId?: string) {
  const url = sessionId ? `${API_BASE}/api/history?session_id=${sessionId}` : `${API_BASE}/api/history`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<{ items: AuditEntry[]; total: number }>;
}

export async function getSchema() {
  const res = await fetch(`${API_BASE}/api/schema`);
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<{ tables: SchemaTable[] }>;
}
