import { useMutation, type UseMutationResult } from "@tanstack/react-query";

import {
  assistantApi,
  type AssistantDesignRequest,
  type AssistantDesignResponse,
} from "@/api";

import { useAssistantChatStore } from "./assistantChatStore";

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

/** Variables for {@link useAssistantChatSend}: the request + where it belongs. */
export interface AssistantChatSendVars {
  /** Session key (see `chatKey`) captured at send time. */
  chatKey: string;
  /** The session generation at send time ("New chat" bumps it). */
  generation: number;
  body: AssistantDesignRequest;
}

/**
 * The assistant mutation wired to the in-memory chat store (task 11.5).
 *
 * The success/error handlers are MUTATION-level options (not `mutate()`
 * callbacks), so React Query still runs them after the chat panel unmounts:
 * a reply that arrives while the panel is closed (or after navigating away)
 * still lands in the conversation it was sent from.
 */
export function useAssistantChatSend(): UseMutationResult<
  AssistantDesignResponse,
  Error,
  AssistantChatSendVars
> {
  return useMutation<AssistantDesignResponse, Error, AssistantChatSendVars>({
    mutationFn: ({ body }) => assistantApi.design(body),
    onSuccess: (res, { chatKey, generation }) =>
      useAssistantChatStore.getState().receiveReply(chatKey, generation, res),
    onError: (err, { chatKey, generation }) =>
      useAssistantChatStore.getState().receiveError(chatKey, generation, err),
  });
}
