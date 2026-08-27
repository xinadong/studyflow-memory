import { describe, expect, it } from 'vitest'
import { memoryTypeLabels, statusLabels } from '../types'

describe('display mappings', () => {
  it('labels every backend memory state used by the UI', () => {
    expect(memoryTypeLabels.knowledge_state).toBe('知识状态')
    expect(memoryTypeLabels.recovery_experience).toBe('恢复经验')
    expect(statusLabels.pending).toBe('待确认')
    expect(statusLabels.confirmed).toBe('已确认')
  })
})
