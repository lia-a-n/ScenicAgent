import type { StreamEvent } from '../types'

/**
 * 以 fetch + ReadableStream 方式消费 SSE
 * (EventSource 不支持 POST,这里用 POST 携带 session_id 与消息体)
 */
export async function streamChat(
  sessionId: string,
  message: string,
  onEvent: (ev: StreamEvent) => void,
): Promise<void> {
  const resp = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, message }),
  })

  if (!resp.ok || !resp.body) {
    throw new Error(`服务异常(${resp.status})`)
  }

  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      // SSE 事件以空行分隔
      const blocks = buffer.split('\n\n')
      buffer = blocks.pop() ?? ''
      for (const block of blocks) {
        const line = block.split('\n').find((l) => l.startsWith('data: '))
        if (!line) continue
        try {
          onEvent(JSON.parse(line.slice(6)))
        } catch (err) {
          // 单个事件处理失败不能中断整条流
          console.error('[sse] 事件处理异常:', err, line)
        }
      }
    }
  } finally {
    // 正常结束或中途取消都释放 reader
    reader.releaseLock()
  }
}

/** 首次进入生成持久化会话 ID */
export function getSessionId(): string {
  let sid = localStorage.getItem('scenic_sid')
  if (!sid) {
    sid = 'h5-' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
    localStorage.setItem('scenic_sid', sid)
  }
  return sid
}
