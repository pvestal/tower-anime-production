import { defineStore } from 'pinia'
import { ref } from 'vue'
import { feedbackApi } from '@/api/feedback'
import type { FeedbackQuestion, AnswerResponse, FeedbackRound } from '@/api/feedback'

export const useFeedbackStore = defineStore('feedback', () => {
  // Active feedback state (per shot)
  const activeShotId = ref<string | null>(null)
  const feedbackId = ref<string | null>(null)
  const questions = ref<FeedbackQuestion[]>([])
  const echoContext = ref('')
  const feedbackRound = ref(0)
  const lastAnswer = ref<AnswerResponse | null>(null)
  const history = ref<FeedbackRound[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function submitReview(shotId: string, rating: number, text: string, categories: string[]) {
    loading.value = true
    error.value = null
    try {
      const resp = await feedbackApi.submitReview(shotId, rating, text, categories)
      activeShotId.value = shotId
      feedbackId.value = resp.feedback_id
      questions.value = resp.questions
      echoContext.value = resp.echo_context
      feedbackRound.value = resp.feedback_round
      lastAnswer.value = null
      return resp
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to submit feedback'
      throw err
    } finally {
      loading.value = false
    }
  }

  async function answerQuestion(
    questionId: string,
    selectedOption: string,
    extraParams?: Record<string, unknown>,
  ) {
    if (!activeShotId.value || !feedbackId.value) return
    loading.value = true
    error.value = null
    try {
      const resp = await feedbackApi.answerQuestion(
        activeShotId.value,
        feedbackId.value,
        questionId,
        selectedOption,
        extraParams,
      )
      lastAnswer.value = resp
      return resp
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to apply action'
      throw err
    } finally {
      loading.value = false
    }
  }

  async function fetchHistory(shotId: string) {
    try {
      const resp = await feedbackApi.getHistory(shotId)
      history.value = resp.rounds
    } catch {
      // Non-fatal
    }
  }

  function reset() {
    activeShotId.value = null
    feedbackId.value = null
    questions.value = []
    echoContext.value = ''
    feedbackRound.value = 0
    lastAnswer.value = null
    error.value = null
  }

  return {
    activeShotId,
    feedbackId,
    questions,
    echoContext,
    feedbackRound,
    lastAnswer,
    history,
    loading,
    error,
    submitReview,
    answerQuestion,
    fetchHistory,
    reset,
  }
})
