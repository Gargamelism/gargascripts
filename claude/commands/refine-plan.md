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
