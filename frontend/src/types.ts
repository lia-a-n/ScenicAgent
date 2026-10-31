/* SSE 事件与前端消息类型 */

export interface Source {
  title: string
  source: string
  score: number
}

export interface ItineraryStep {
  time: string
  poi_name: string
  activity: string
  tip?: string
}

export interface Itinerary {
  date: string
  weather_summary: string
  constraints_used: string
  has_elder: boolean
  child_ages: number[]
  steps: ItineraryStep[]
  rainy_fallback?: string
  warnings?: string[]
}

export interface HandoffInfo {
  ticket_id: string
  category: string
  reason?: string
}

export interface ToolEvent {
  id: number
  tool: string
  label: string
  detail: string
  done: boolean
}

export type ChatRole = 'user' | 'assistant'

export interface ChatMessage {
  id: string
  role: ChatRole
  content: string
  streaming?: boolean
  sources?: Source[]
  itinerary?: Itinerary
  handoff?: HandoffInfo
  tools?: ToolEvent[]
}

/* 后端 SSE 事件 */
export interface StreamEvent {
  type: 'intent' | 'sources' | 'token' | 'tool_start' | 'tool_end' | 'itinerary' | 'handoff' | 'done' | 'error'
  intent?: string
  confidence?: number
  chunk?: string
  sources?: Source[]
  tool?: string
  args?: Record<string, any>
  result?: string
  itinerary?: Itinerary
  ticket_id?: string
  category?: string
  reason?: string
  message?: string
}

export interface StreamHandlers {
  onEvent: (ev: StreamEvent) => void
}
