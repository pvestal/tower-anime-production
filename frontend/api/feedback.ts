/**
 * Feedback Loop API client — submit reviews, answer questions, get history.
 */
import { createRequest } from './base'

const request = createRequest('/api/feedback')

export interface FeedbackOption {
  id: string
  label: string
  action: string
  params?: Record<string, unknown>
}

export interface FeedbackQuestion {
  id: string
  text: string
  options: FeedbackOption[]
}

export interface ReviewResponse {
  feedback_id: string
  questions: FeedbackQuestion[]
  echo_context: string
  feedback_round: number
}

export interface AnswerResponse {
  action_type: string
  changes: Record<string, { before: unknown; after: unknown }>
  regenerated: boolean
  before: Record<string, unknown>
  after: Record<string, unknown>
}

export interface FeedbackRound {
  id: string
  shot_id: string
  rating: number
  feedback_text: string
  feedback_categories: string[]
  questions: FeedbackQuestion[]
  answers: Array<Record<string, unknown>>
  actions_taken: Array<Record<string, unknown>>
  echo_context: string
  previous_params: Record<string, unknown> | null
  new_params: Record<string, unknown> | null
  feedback_round: number
  created_at: string | null
}

export const feedbackApi = {
  submitReview(shotId: string, rating: number, text: string, categories: string[]) {
    return request<ReviewResponse>('/review', {
      method: 'POST',
      body: JSON.stringify({
        shot_id: shotId,
        rating,
        feedback_text: text,
        feedback_categories: categories,
      }),
    })
  },

  answerQuestion(
    shotId: string,
    feedbackId: string,
    questionId: string,
    selectedOption: string,
    extraParams?: Record<string, unknown>,
  ) {
    return request<AnswerResponse>('/answer', {
      method: 'POST',
      body: JSON.stringify({
        shot_id: shotId,
        feedback_id: feedbackId,
        question_id: questionId,
        selected_option: selectedOption,
        extra_params: extraParams,
      }),
    })
  },

  getHistory(shotId: string) {
    return request<{ shot_id: string; rounds: FeedbackRound[]; total: number }>(
      `/history/${shotId}`,
    )
  },
}
