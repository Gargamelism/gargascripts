Iteratively refine a plan file to full resolution using parallel research agents — never implementing, only planning.

## Target file

!`cat "$ARGUMENTS"`

## Instructions

You are operating in **plan-only mode**. Your only permitted actions are:
- Reading files (any file in the codebase)
- Launching Explore subagents in parallel
- Editing the plan file at the path: **$ARGUMENTS**

You must NEVER write implementation code or modify any file other than the plan file.

### Iteration loop

Repeat the following until the plan is fully resolved:

**Step 1 — Audit** (re-read the plan file each iteration using the Read tool):
Identify all unresolved items:
- Vague or hand-wavy descriptions
- Missing specifics: file paths, function names, data structures, API shapes
- Open questions, TODOs, or "TBD" sections
- Assumed knowledge not yet established in the plan
- Undecided architectural choices
- Sections where the next developer would have to guess

**Also audit the plan against these code quality principles** — flag any that the plan fails to address:
1. **DRY** — Does the plan avoid duplicating logic that already exists?
2. **Don't Reinvent the Wheel** — Does the plan leverage existing libraries instead of hand-rolling standard functionality?
3. **Naming** — Are proposed names clear, unambiguous, and free of vague terms?
4. **KISS** — Is the proposed solution as simple as the problem allows? No unnecessary abstraction?
5. **YAGNI** — Does the plan avoid scaffolding for future use cases that aren't needed now?
6. **OCP** — Is new behavior additive? Can it be extended without modifying existing internals?
7. **Separation of Concerns** — Are distinct responsibilities (IO, business logic, presentation) kept separate?
8. **Encapsulation** — Are implementation details hidden behind appropriate interfaces?
9. **Testability** — Are dependencies injected? Is global mutable state avoided?
10. **Fail Fast** — Does the plan surface errors immediately rather than deferring or silently swallowing them?
11. **Functional / Declarative** — Does the plan prefer declarative patterns over imperative mutation where clarity is equal or better?
12. **Readability over Cleverness** — Does the plan avoid clever tricks that sacrifice readability?
13. **Secure at Core** — Does the plan prevent secrets/PII from leaking externally or credentials from being hardcoded?
14. **Security Scrutiny** — Does the plan validate/sanitize inputs, use dependency versions free of known CVEs, and enforce proper access controls?
15. **Readability & Configurability** — Does the plan use named constants for static values and config/env vars for dynamic ones (no magic numbers/strings)?
16. **Test Coverage** — Does the plan include tests for edge cases and failure paths, with assertions that test behavior not implementation?
17. **Privacy** — Does the plan handle PII/PHI with care: not logged, not sent to third parties unnecessarily, stored with encryption and access controls?

Each violated principle is an unresolved item — treat it the same as any other gap and address it in Steps 2–3.

If none remain, stop and emit `PLAN COMPLETE`.

**Step 2 — Research** (parallel agents):
For each unresolved item, launch an Explore agent with a focused search task.
- Prefer launching multiple agents IN PARALLEL (single message, multiple Agent tool calls)
- Use up to 3 agents per iteration
- Each agent must have a specific, narrow search focus
- Agents may read any file

**Step 3 — Update the plan**:
Edit the plan file ($ARGUMENTS) with concrete findings:
- Replace vague language with specific decisions
- Add file paths, function signatures, existing patterns found
- Resolve open questions with researched answers
- Add pseudocode or data-structure sketches where helpful (not implementation code)
- Never remove sections — only enrich them
- **Prefer parallel implementation structure**: organize tasks so independent steps are clearly marked as parallelizable, group dependent steps explicitly, and flag what can be done simultaneously vs sequentially

**Step 4 — Report**:
Briefly output what was unresolved, what each agent found, and what was updated. Then loop back to Step 1.

### Definition of "fully resolved"

The plan is complete when every section could be handed to a developer with no ambiguity — specific files named, existing utilities identified, data flows described, edge cases listed, no TODOs remaining, and tasks organized to maximize parallelism.

## Output

After completing all iterations, output:

**PLAN COMPLETE — all details resolved.**

Followed by a concise summary of the final plan's key decisions.
