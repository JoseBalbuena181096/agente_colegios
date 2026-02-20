# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI-powered admissions assistant ("Luca") for Colegio San Angel (3 planteles: Puebla, Poza Rica, Coatzacoalcos). The bot qualifies prospective parents/tutors via Facebook, Instagram, WhatsApp, and SMS through GoHighLevel (GHL) webhooks, collects 5 data points (plantel, nivel educativo, nombre del padre/tutor, telefono, email), and schedules appointments with advisors via round-robin booking links.

The bot identity is **Luca** with the community mascot **Grizzlies** and emoji **bear**.

Forked from the Universidad de Oriente ("Max") system. Key differences:
- 3 planteles instead of 5 campuses
- K-12 levels (Preescolar, Primaria, Secundaria, Bachillerato) instead of university programs (licenciaturas, maestrias, etc.)
- "Plantel" terminology instead of "Campus" in user-facing text
- Collects parent/tutor name (not student name) + nivel educativo (not carrera)
- Domain: sanangel.edu.mx (not uo.edu.mx)

## Commands

```bash
# Run locally
uvicorn main:app --host 0.0.0.0 --port 8000

# Run tests
python -m pytest tests/ -v

# Install dependencies
pip install -r requirements.txt
```

Deployed on Railway via Nixpacks (`railway.json`). Procfile runs uvicorn.

## Architecture

**FastAPI app** (`main.py`) with two thin routers that delegate to an orchestrator and specialized services.

### Webhook Endpoints (Routers)
- **`app/routers/conversations.py`** — `POST /webhook_conversations`: Thin HTTP layer (~30 lines). Extracts payload via `payload_service`, then delegates entirely to `ConversationOrchestrator.process()`.
- **`app/routers/social.py`** — `POST /webhook_facebook` and `POST /webhook_instagram`: Handle public comments on posts/reels. Classify interest via `comment_agent`, send DMs to relevant leads, and toggle GHL custom field flags.

### Orchestrator (`app/services/orchestrator_service.py`)
- **`ConversationOrchestrator`** — Contains the full 12-step conversation pipeline, decoupled from HTTP. Receives all services via constructor injection. Handles: history loading, human takeover detection, handoff persistence, admin topic filter, lead state management, safety nets, AI agent invocation, loop detection, lead scoring, campus transfer, booking link injection, and response dispatch.

### AI Agents (LangGraph)
- **`app/agents/career_agent.py`** — Main sales agent. LangGraph graph with 5 nodes: `enrich` (regex phone/email injection) → `kill_switch_check` (lead_state completeness check + regex fallback) → `agent` (LLM call with campus + objection tools) → `tools` (campus lookup + objection playbook) → `format` (deterministic response formatting, NO second LLM call). Uses `{BOOKING_LINK}` placeholder resolved downstream. Supports two prompt modes: normal (data collection) and post-booking (restrictive).
- **`app/agents/comment_agent.py`** — Comment classifier. Single-node LangGraph graph. Uses structured output (`AgentResponse`) to classify interest (True/False), then returns a hardcoded WhatsApp redirect message for relevant leads.

### Services (`app/services/`)
- **`orchestrator_service.py`** — `ConversationOrchestrator` class. Full conversation pipeline extracted from the router. All business logic lives here, HTTP-independent.
- **`supabase_client.py`** — Singleton Supabase client. All services share a single `Client` instance via `get_supabase()`. Centralizes credential validation.
- **`campus_registry.py`** — `CampusRegistry` singleton. Single source of truth for all plantel data (location IDs, tokens, keywords, name mappings). Location IDs: Puebla=`SOz5nfbI23Xm9mXC51bI`, Poza Rica=`epK2kqk7MkT8t0OBudqP`, Coatzacoalcos=`UNorB3dhUdmtfbdjMAOc`.
- **`ghl_service.py`** — GoHighLevel API client. Multi-plantel support via `CampusRegistry` (injected). Handles send message, contact CRUD, tags, notes, and campus transfers.
- **`conversation_service.py`** — Supabase persistence via `get_supabase()`. Manages `conversations` and `messages` tables. Handles human takeover flags, conversation migration on campus transfer.
- **`lead_state_service.py`** — Supabase CRUD for `lead_states` table via `get_supabase()`. Tracks the 5 data points per lead, booking status, post-booking interaction count, and lead score. Auto-recalculates `current_step` and `is_complete` on every update.
- **`objection_service.py`** — Loads `objection_playbook` table into memory cache at startup via `get_supabase()`. Matches user messages against trigger keywords sorted by priority.
- **`lead_scoring_service.py`** — Deterministic scoring (no LLM) with signals totaling 0-150+ points. Maps scores to 4 tiers: Lead Frio (0-25), Lead Tibio (26-50), Lead Caliente (51-80), Lead Urgente (81+).
- **`payload_service.py`** — Webhook payload normalization. Extracts `WebhookData` from raw GHL payloads. Contains anti-loop filters, reaction/like/story mention detection, and lead form parsing.
- **`response_service.py`** — Pre-send validation, booking link injection (Priority 0: reuse from history → Priority 1: GHL assigned advisor → Priority 2: round-robin), GHL message dispatch with WhatsApp fallback, and scoring tag management.
- **`safety_net_service.py`** — Deterministic bypass logic. Checks for human request keywords, admin topics (boleta, etc.), booking-sent state with post-booking count, and greeting loops.
- **`loop_detector.py`** — Semantic loop detection using `difflib.SequenceMatcher`. Two thresholds: pre-LLM (0.70) and post-LLM (0.95).
- **`advisor_service.py`** — Round-robin advisor assignment from Supabase `advisors` table by `location_id`.
- **`llm_client.py`** — LLM provider abstraction. Supports Google Gemini and OpenAI.
- **`campus_service.py`** — Supabase queries for campus and career/level data. `get_campus_by_name()` with space-normalized fallback.
- **`apify_service.py`** — Facebook/Instagram post scraping via Apify for comment context.

### Tools (`app/tools/`)
- **`campus_tools.py`** — LangChain tools for plantel info and nivel educativo listings from Supabase.
- **`objection_tools.py`** — LangChain tool `get_objection_response(topic)` that queries the objection playbook service.

### Infrastructure
- **`app/logging_config.py`** — Structured logging configuration. All modules use `logging.getLogger(__name__)`.

### Key Patterns
- **Singleton services** initialized in `app/dependencies.py` and imported by routers/orchestrator.
- **Singleton Supabase client**: All DB services call `get_supabase()` from `app/services/supabase_client.py`.
- **Campus Registry**: `CampusRegistry` in `app/services/campus_registry.py` is the single source of truth for plantel data. Injected into `GHLService` and `AdvisorService` via constructor.
- **Orchestrator pattern**: `conversations.py` router is a thin HTTP layer (~30 lines). All business logic lives in `ConversationOrchestrator`.
- **Structured logging**: All modules use `logging.getLogger(__name__)` with levels `info/warning/error`. No `print()` calls.
- **Multi-plantel routing**: Every GHL API call requires the correct `location_id` to select the right auth token. `CampusRegistry` maps `location_id` → plantel config.
- **Bot message signature**: The bot prepends a zero-width space (`\u200B`) to outgoing messages for human takeover detection.
- **`{BOOKING_LINK}` placeholder**: The LLM outputs `{BOOKING_LINK}`, resolved to a real advisor booking URL by `response_service.inject_booking_link()`.
- **Advisor lookup**: `get_next_advisor()` queries `advisors` by `location_id`. Always pass the raw `location_id`, **never** a campus name. Always null-check with fallback.
- **Kill switch**: Checks `lead_state.is_complete` first, regex fallback. **Skipped in post-booking mode**.
- **Dynamic system prompt**: `get_system_prompt()` injects `## ESTADO ACTUAL DEL PROSPECTO` showing confirmed vs pending data fields.
- **Post-booking mode**: After booking link is sent, 1 response then handoff + permanent bot silence via `set_human_active`.
- **Lead scoring**: Deterministic 0-150+ score. GHL tags updated automatically.
- **Campus name normalization**: `campus_service.get_campus_by_name()` uses ILIKE first, then space-stripped comparison.
- **URL anti-hallucination guardrail**: `format_response_node` validates all `sanangel.edu.mx` URLs against tool results.
- **CODE_LEAK recovery**: When Gemini generates tool-call code as text, `_recover_from_code_leak()` executes the tool directly.

### Database (Supabase/PostgreSQL)
Unified schema in `database/schema.sql` — creates all 7 tables, triggers, indexes, and seed data in one file.

| Table | Description |
|-------|-------------|
| `conversations` | Per contact_id, with `is_human_active` flag for human takeover |
| `messages` | Role + content + metadata JSONB, ordered chronologically |
| `campuses` | 3 planteles (Puebla, Poza Rica, Coatzacoalcos) with address, phone, `website_url`, `location_id` |
| `careers` | Niveles educativos per plantel (preescolar, primaria, secundaria, bachillerato) with `website_url` and `program_type` |
| `lead_states` | 5 data fields (campus, programa, nombre_completo, telefono, email) + `current_step`, `is_complete`, `booking_sent_at`, `post_booking_count`, `score`, `channel` |
| `advisors` | Round-robin advisor catalog with `booking_link`, `location_id`, `ghl_user_id` |
| `objection_playbook` | 9 K-12 objections: `trigger_keywords TEXT[]`, `category`, `response_template`, `redirect_to_booking`, `priority` |

**SQL Files:**
- `database/schema.sql` — Full schema + seed data (campuses, careers, objection_playbook). Run this first.
- `database/seed_only.sql` — Re-populate config data without recreating tables.
- `database/cleanup.sql` — TRUNCATE transactional data (conversations, messages, lead_states) keeping config intact.

**Seed data included in schema.sql:**
- 3 campuses with real `location_id` values matching `campus_registry.py`
- 11 niveles educativos (Puebla: 4, Poza Rica: 3 — no Preescolar, Coatzacoalcos: 4)
- 9 objection playbook entries adapted for K-12 context (colegiaturas, becas, horarios, transporte, modelo educativo, instalaciones, inscripcion, uniformes, ubicacion)
- Advisor inserts are commented out as placeholders — uncomment with real data

### Models
- **`app/models/response_models.py`** — `AgentResponse` (Pydantic): structured LLM output with `is_relevant_query`, `message`, `detected_campus`, `captured_data`. `MessageAnalysis`: used by Apify scrape decision.

## Key Domain Concepts
- **Location ID**: GHL sub-account identifier per plantel. Defined in `CampusRegistry._CAMPUS_DATA`. Puebla=`SOz5nfbI23Xm9mXC51bI`, Poza Rica=`epK2kqk7MkT8t0OBudqP`, Coatzacoalcos=`UNorB3dhUdmtfbdjMAOc`.
- **Contact ID**: GHL contact identifier. One conversation per contact_id in Supabase.
- **Human Takeover**: When a human agent replies in GHL, the bot detects the unrecognized outbound message and permanently silences itself for that contact.
- **Handoff**: Bot sends a final message (booking link or "un asesor te contactara") and stops responding for 30 minutes.
- **Campus Transfer**: If a user mentions a different plantel, the system creates a new contact in the target GHL sub-account, migrates the Supabase conversation, and sends history as a note.
- **Lead State**: Persistent record of captured data per lead. Drives the dynamic system prompt, kill switch, and post-booking logic.
- **Post-Booking Mode**: Restrictive agent mode after booking link is sent. Max 1 interaction, then human handoff + permanent bot silence.
- **Lead Score**: Deterministic 0-150+ score. Maps to GHL tags for advisor prioritization.
- **Objection Playbook**: Supabase-backed table of standardized responses to common objections.

## Pipeline Flow (orchestrator_service.py)

```
Router: Extract payload (payload_service) → check should_ignore → orchestrator.process(data)

Orchestrator.process():
1. Resolve missing conversation_id (GHL API fallback)
2. Early Persistence (conversation DB)
3. Load History + Human Takeover Check (_check_human_takeover)
4. Handoff Persistence Check (_check_handoff_persistence)
5. Admin Topic Filter (safety_net_service)
6. Lead State Persistence (get_or_create + pre-capture phone/lead_form)
7. AI Agent Pipeline:
   a. Pre-LLM Loop Detection → _handle_pre_llm_loop
   b. Post-Booking Check (1+ = handoff + permanent silence / 0 = restrictive prompt)
   c. Safety Nets (human request / complete data bypass)
   d. Build LangChain History (_build_messages_history) + Inject phone/lead_form
   e. Invoke career_agent (with lead_state + post_booking_mode)
      - kill_switch skipped if post_booking_mode
      - CODE_LEAK recovery: if LLM outputs tool code as text, execute tool directly
      - format_response_node validates sanangel.edu.mx URLs against tool results
      - URL auto-injection: if LLM mentions level without URL, inject from tool results
   f. Post-LLM Loop Prevention → _handle_post_llm_loop
   g. Update lead_state with captured_data
   h. Mark booking sent (if applicable)
   i. Calculate & persist lead score
   j. Campus Transfer (_handle_campus_transfer)
   k. Booking Link Injection (reuse from history → assigned advisor → round-robin)
   l. Send Response + Update Tags + Scoring Tags + Save to DB
```

## Setup Checklist (Before First Deploy)

1. ~~Replace placeholder location IDs in `app/services/campus_registry.py`~~ **DONE** — Puebla=`SOz5nfbI23Xm9mXC51bI`, Poza Rica=`epK2kqk7MkT8t0OBudqP`, Coatzacoalcos=`UNorB3dhUdmtfbdjMAOc`
2. Set all `.env` variables (see `.env.example`)
3. Run `database/schema.sql` in Supabase SQL Editor — creates all 7 tables with seed data (campuses, niveles educativos, objection playbook)
4. Uncomment and populate `advisors` table with real advisor data and booking links
5. Replace placeholder booking links in `app/services/response_service.py` and `app/services/advisor_service.py`
6. Configure GHL webhooks to point to `/webhook_conversations`, `/webhook_facebook`, `/webhook_instagram`
