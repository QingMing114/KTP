/** Canonical conversation client — CRUD /api/product/v1/conversations. */

import { canonicalJson } from './request'

export interface CanonicalConversation {
  conversation_id: string
  title: string
  created_at?: string
  updated_at?: string
}

export interface ConversationListResponse {
  items: CanonicalConversation[]
  next_cursor?: string
  has_more?: boolean
}

export async function createConversation(title?: string): Promise<CanonicalConversation> {
  return canonicalJson<CanonicalConversation>('/conversations', {
    method: 'POST',
    body: JSON.stringify({ title: title ?? 'New conversation' }),
  })
}

export async function listConversations(): Promise<CanonicalConversation[]> {
  const resp = await canonicalJson<ConversationListResponse>('/conversations')
  return resp.items
}

export async function getConversation(conversationId: string): Promise<CanonicalConversation> {
  return canonicalJson<CanonicalConversation>(`/conversations/${encodeURIComponent(conversationId)}`)
}

export async function updateConversation(conversationId: string, title: string): Promise<CanonicalConversation> {
  return canonicalJson<CanonicalConversation>(`/conversations/${encodeURIComponent(conversationId)}`, {
    method: 'PATCH',
    body: JSON.stringify({ title }),
  })
}

export async function deleteConversation(conversationId: string): Promise<void> {
  await canonicalJson(`/conversations/${encodeURIComponent(conversationId)}`, { method: 'DELETE' })
}
