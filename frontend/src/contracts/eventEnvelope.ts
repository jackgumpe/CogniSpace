import { z } from "zod";

export const EventEnvelopeSchema = z.object({
  schema_version: z.string(),
  event_id: z.string(),
  parent_event_id: z.string().nullable().optional(),
  session_id: z.string(),
  trace_id: z.string(),
  timestamp_utc: z.string(),
  actor_id: z.string(),
  actor_role: z.enum(["PM", "LEAD", "DEV", "AUDITOR", "SYSTEM", "USER"]),
  channel: z.enum(["GLOBAL", "LOCAL", "SYSTEM", "AUTOPROMPT"]),
  event_type: z.string(),
  payload: z.record(z.unknown()),
  safety_flags: z.array(z.string()).default([]),
  token_in: z.number().int().nonnegative().default(0),
  token_out: z.number().int().nonnegative().default(0),
  latency_ms: z.number().int().nonnegative().default(0),
  cost_usd: z.number().nonnegative().default(0)
});

export type EventEnvelope = z.infer<typeof EventEnvelopeSchema>;
