# BE Server Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split large BE service modules into focused packages and introduce injectable game policy objects.

**Architecture:** Convert `app.be.services.game` and `app.be.services.match` from single modules into packages with compatibility re-exports. Keep behavior stable while extracting pure game policies from `GameService` and separating match WebSocket management, message handling, timers, broadcasters, and snapshots.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy async repositories, pytest, ruff.

---

## File Structure

- Create `app/be/services/game/records.py` for existing game DTO dataclasses and constants that are DTO defaults.
- Create `app/be/services/game/repository_protocol.py` for `GameRepositoryProtocol`.
- Create `app/be/services/game/errors.py` for game AppException subclasses.
- Create `app/be/services/game/session_participant_policy.py` for participant construction.
- Create `app/be/services/game/session_credential_policy.py` for token issue/hash/expiry policy.
- Create `app/be/services/game/room_membership_policy.py` for solo-session abort decisions.
- Create `app/be/services/game/service.py` for `GameService`.
- Create `app/be/services/game/__init__.py` to re-export the existing public API.
- Create `app/be/services/match/snapshots.py` for snapshot DTO dataclasses.
- Create `app/be/services/match/timers.py` for timer dataclasses and timer extraction.
- Create `app/be/services/match/connection_manager.py` for `MatchConnectionManager`.
- Create `app/be/services/match/broadcasters.py` for round event fan-out.
- Create `app/be/services/match/message_handler.py` for command handling.
- Create `app/be/services/match/repository_protocol.py` for `MatchRepositoryProtocol`.
- Create `app/be/services/match/service.py` for `MatchService` and `EmptyMatchRepository`.
- Create `app/be/services/match/__init__.py` to re-export the existing public API.
- Remove old module files after package equivalents exist.

### Task 1: Add GameService Policy Injection Test

**Files:**
- Modify: `test/test_game_session_entry.py`

- [ ] **Step 1: Write the failing test**

Add a service-level test that constructs `GameService(repository, participant_policy=CustomPolicy())`, starts a session, and asserts the custom policy produced the participant display names.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest test/test_game_session_entry.py::test_game_service_uses_injected_session_participant_policy -q`

Expected: FAIL because `GameService.__init__` does not accept `participant_policy`.

### Task 2: Split Game Service and Add Policies

**Files:**
- Create: files under `app/be/services/game/`
- Remove: `app/be/services/game.py`

- [ ] **Step 1: Move records, protocol, errors, and helpers into focused modules**
- [ ] **Step 2: Add `SessionParticipantPolicy`, `SessionCredentialPolicy`, and `RoomMembershipPolicy`**
- [ ] **Step 3: Update `GameService` to accept optional policy objects and delegate participant/token/solo-session decisions**
- [ ] **Step 4: Re-export existing public names in `app/be/services/game/__init__.py`**
- [ ] **Step 5: Run the new test and targeted game tests**

### Task 3: Split Match Service

**Files:**
- Create: files under `app/be/services/match/`
- Remove: `app/be/services/match.py`

- [ ] **Step 1: Move snapshot dataclasses and repository protocol into focused modules**
- [ ] **Step 2: Move `MatchConnectionManager` into `connection_manager.py`**
- [ ] **Step 3: Move timer helpers into `timers.py`**
- [ ] **Step 4: Move round broadcast helpers into `broadcasters.py`**
- [ ] **Step 5: Move `handle_match_message` into `message_handler.py`**
- [ ] **Step 6: Re-export existing public names in `app/be/services/match/__init__.py`**
- [ ] **Step 7: Run targeted match tests**

### Task 4: Clean Imports and Verify

**Files:**
- Modify import lines only where internal modules benefit from direct submodule imports.
- Modify `llm-wiki/wiki/code-conventions.md` or a new decision page only if the final policy boundary becomes an ongoing AI work rule.
- Modify `llm-wiki/index.md` and `llm-wiki/log.md` if LLM Wiki content changes.

- [ ] **Step 1: Run `ruff` format/check command available in the repo**
- [ ] **Step 2: Run full or targeted pytest based on churn**
- [ ] **Step 3: Inspect `git diff --stat` and largest files to confirm the refactor reduced concentration**
