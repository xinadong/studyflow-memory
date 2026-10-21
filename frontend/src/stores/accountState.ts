import { usePlanStore } from './plan'
import { useSessionStore } from './session'
import { useTutorStore } from './tutor'

const ACTIVE_ACCOUNT_KEY = 'studyflow-active-account-id'
const ACCOUNT_SCOPED_KEYS = [
  'studyflow-focus-task-id',
  'studyflow-focus-remaining-seconds',
  'studyflow-plan',
  'studyflow-plan-statuses',
  'studyflow-plan-adjustment',
  'studyflow-review-tasks',
  'studyflow-tutor-config',
  'studyflow-tutor-messages',
  'studyflow-block',
]

export function resetAccountScopedState() {
  useSessionStore().resetAccountState()
  usePlanStore().resetAccountState()
  useTutorStore().clear()
  ACCOUNT_SCOPED_KEYS.forEach(key => sessionStorage.removeItem(key))
}

export function syncAccountScopedState(userId: string | null) {
  const previousUserId = sessionStorage.getItem(ACTIVE_ACCOUNT_KEY)
  if (previousUserId !== userId) resetAccountScopedState()

  if (userId) sessionStorage.setItem(ACTIVE_ACCOUNT_KEY, userId)
  else sessionStorage.removeItem(ACTIVE_ACCOUNT_KEY)
}
