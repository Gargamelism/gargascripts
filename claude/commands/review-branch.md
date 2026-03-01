Review the git branch changes against core code quality principles.

## Branch diff vs base

Base branch (main or master or $ARGUMENTS):

!`BASE=${ARGUMENTS:-$(git branch -r | grep -E 'origin/(main|master)$' | head -1 | sed 's|.*origin/||' | xargs)}; MERGE_BASE=$(git merge-base HEAD $BASE 2>/dev/null || git merge-base HEAD main 2>/dev/null || git merge-base HEAD master 2>/dev/null); echo "Base branch: $BASE"; echo "Merge base: $MERGE_BASE"; echo ""; echo "=== Changed files ==="; git diff --name-status $MERGE_BASE..HEAD; echo ""; echo "=== Full diff ==="; git diff $MERGE_BASE..HEAD`

!`echo "=== Recent commits on this branch ==="; git log $(git merge-base HEAD ${ARGUMENTS:-$(git branch -r | grep -E 'origin/(main|master)$' | head -1 | sed 's|.*origin/||' | xargs)} 2>/dev/null)..HEAD --oneline 2>/dev/null || git log --oneline -10`

## Review Instructions

Analyze the diff above and evaluate against each principle below. For each finding include:
- The principle violated
- Severity: **MUST-FIX** | **SUGGESTION** | **NITPICK**
- File path and line number(s)
- Concise explanation
- Concrete fix (show code when helpful, keep it brief)

### Principles to check

1. **DRY** — Similar logic should be implemented once. Flag copy-pasted blocks or near-duplicates that should be extracted.
2. **Don't Reinvent the Wheel** — If doing something standard (parsing, HTTP, date math, etc.), a library should be used instead of a hand-rolled implementation.
3. **Naming** — No non-standard acronyms, no single-letter variables (except conventional loop indices like `i`, `j`), no vague names (`data`, `info`, `temp`, `stuff`).
4. **Keep It Simple (KISS)** — Prefer simple solutions over configurable/generalized ones. Flag unnecessary abstraction layers or over-engineering.
5. **YAGNI** — No code scaffolded for future use that isn't needed now. Flag abstract base classes, extension points, or placeholder logic with no current consumer.
6. **OCP (Open/Closed)** — Logic boxes should be easy to extend (add new behavior) without modifying existing code. Flag places where adding a new case requires editing existing internals.
7. **Separation of Concerns** — Different responsibilities should live in different units. Flag functions/classes that mix IO with logic, business rules with presentation, etc.
8. **Encapsulation** — Implementation details should be hidden. Flag direct field access on objects that should expose methods, or leaking internal state.
9. **Testability** — Dependencies should be injected, not hard-coded. No global mutable state. Functions should minimize side effects. Flag code that would be hard to unit test.
10. **Fail Fast** — Errors and invalid states should be surfaced immediately, not silently swallowed. Flag places where validation is deferred or errors are caught and ignored.
11. **Functional / Declarative** — Prefer declarative expressions (`map`, `filter`, `reduce`, comprehensions, pipelines) over imperative loops with mutation where readability is equal or better.
12. **Readability over Cleverness** — Flag clever one-liners, obscure tricks, or dense logic that sacrifices readability. Simple and clear wins.
13. **Secure at Core** — Flag any place where data could leak externally (logging secrets, sending PII to third parties, storing credentials in code, unvalidated inputs crossing trust boundaries).

## Output Format

Start with a one-paragraph **summary** of overall quality and the most important concerns.

Then group findings by file. Use this structure:

---
### `path/to/file.ts`
- **[PRINCIPLE NAME]** `SEVERITY` — line N: explanation. Fix: ...
---

End with a **verdict**: APPROVE / APPROVE WITH SUGGESTIONS / REQUEST CHANGES, and a bulleted list of the must-fix items if any.
