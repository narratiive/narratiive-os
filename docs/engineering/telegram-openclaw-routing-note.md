# Telegram conversational routing simplification

## Problem

The live n8n/HTTP Telegram path was posting ordinary language to `/telegram/inbound`, where `LeadAwareTonyApplication` unconditionally called the deterministic command service. That allowed `TonyConversationalIntentCommandService` to answer normal sentences with routing leakage such as “conversational request” and “system command”, even though the direct OpenClaw `/v1/responses` acceptance probe was healthy.

## Decision

Use the same routing rule at every Telegram ingress:

- ordinary language -> Tony's OpenClaw agent runtime
- explicit `/slash` commands -> Narratiive OS deterministic command surface

OpenClaw owns semantic interpretation and durable conversational context. Narratiive OS continues to own business state, approvals, evidence, audit, deterministic effects and explicit operational commands.

## Upstream basis

OpenClaw's OpenResponses endpoint executes through the normal Gateway agent codepath, so the configured Tony workspace, permissions, model and native agent tools apply. OpenClaw also documents isolated agents and sub-agent/session orchestration, so no additional phrase router is required in Narratiive OS for normal conversation.

## Acceptance

The live bridge must send arbitrary natural language, typo variants, contextual follow-ups and specialist-status questions to OpenClaw. It must never fall back to the legacy phrase parser when OpenClaw is unavailable; failures should be explicit. Only messages beginning with `/` may use the deterministic command service.
