import { useMutation, type UseMutationResult } from "@tanstack/react-query";

import {
  assistantApi,
  type AssistantDesignRequest,
  type AssistantDesignResponse,
} from "@/api";

/**
 * React Query mutation for the AI design assistant (task 11.1).
 *
 * Each call POSTs the new user message plus the running conversation
 * `history` and the CURRENT artifact to `POST /api/assistant/design`; the model
 * is called on the backend through the LiteLLM provider layer (never from the
 * browser). The response is either a clarifying question or a validated
 * proposal (`mode`), which the chat panel renders. Provider + model are carried
 * per request in the body.
 */
export function useAssistantDesign(): UseMutationResult<
  AssistantDesignResponse,
  Error,
  AssistantDesignRequest
> {
  return useMutation<AssistantDesignResponse, Error, AssistantDesignRequest>({
    mutationFn: (body) => assistantApi.design(body),
  });
}
