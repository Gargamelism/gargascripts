#!/usr/bin/env bash
# Post-edit hook: runs formatter, linter, and tests on changed files.
# Triggered after Edit, Write, NotebookEdit tool use.
# Exit 0 → clean. Exit 2 → errors fed back to Claude for self-correction.

set -euo pipefail

# ---------- Parse hook input ----------
INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('file_path',''))" 2>/dev/null || true)
CWD=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('cwd',''))" 2>/dev/null || true)

# Nothing to do if no file path
[[ -z "$FILE_PATH" ]] && exit 0

# Resolve to absolute path
if [[ "$FILE_PATH" != /* ]]; then
  FILE_PATH="$CWD/$FILE_PATH"
fi

# Must exist and be a regular file
[[ -f "$FILE_PATH" ]] || exit 0

# ---------- Skip excluded paths ----------
EXCLUDED_PATTERNS=(
  "/node_modules/"
  "/.git/"
  "/__pycache__/"
  "/.venv/"
  "/dist/"
  "/build/"
  "/.next/"
  "/coverage/"
  "/.mypy_cache/"
  "/.ruff_cache/"
  "/.pytest_cache/"
)
for pattern in "${EXCLUDED_PATTERNS[@]}"; do
  if [[ "$FILE_PATH" == *"$pattern"* ]]; then
    exit 0
  fi
done

# ---------- Detect project root + type ----------
detect_project_root() {
  local dir
  dir=$(dirname "$FILE_PATH")
  local markers=("pyproject.toml" "setup.py" "setup.cfg" "package.json")

  while [[ "$dir" != "/" ]]; do
    for marker in "${markers[@]}"; do
      if [[ -f "$dir/$marker" ]]; then
        echo "$dir"
        return 0
      fi
    done
    dir=$(dirname "$dir")
  done

  # Fallback to CWD if it has a marker
  for marker in "${markers[@]}"; do
    if [[ -f "$CWD/$marker" ]]; then
      echo "$CWD"
      return 0
    fi
  done

  echo ""
}

PROJECT_ROOT=$(detect_project_root)
[[ -z "$PROJECT_ROOT" ]] && exit 0

# Determine language
LANG_TYPE=""
if [[ -f "$PROJECT_ROOT/pyproject.toml" ]] || [[ -f "$PROJECT_ROOT/setup.py" ]] || [[ -f "$PROJECT_ROOT/setup.cfg" ]]; then
  LANG_TYPE="python"
fi
if [[ -f "$PROJECT_ROOT/package.json" ]]; then
  # package.json takes precedence for JS/TS files
  EXT="${FILE_PATH##*.}"
  case "$EXT" in
    js|jsx|ts|tsx|mjs|cjs) LANG_TYPE="js" ;;
    py) LANG_TYPE="python" ;;
    *) [[ "$LANG_TYPE" == "" ]] && LANG_TYPE="js" ;;
  esac
fi

[[ -z "$LANG_TYPE" ]] && exit 0

# Accumulate all error output
ERRORS=""

# ---------- PYTHON ----------
if [[ "$LANG_TYPE" == "python" ]]; then
  VENV="$PROJECT_ROOT/.venv"
  [[ -d "$VENV" ]] || exit 0  # No .venv → skip silently

  # --- Formatter (silent auto-fix) ---
  if [[ -x "$VENV/bin/ruff" ]]; then
    "$VENV/bin/ruff" format "$FILE_PATH" 2>/dev/null || true
  elif [[ -x "$VENV/bin/black" ]]; then
    "$VENV/bin/black" --quiet "$FILE_PATH" 2>/dev/null || true
  fi

  # --- Linter ---
  LINT_OUT=""
  if [[ -x "$VENV/bin/ruff" ]]; then
    LINT_OUT=$("$VENV/bin/ruff" check "$FILE_PATH" 2>&1 || true)
  elif [[ -x "$VENV/bin/flake8" ]]; then
    LINT_OUT=$("$VENV/bin/flake8" "$FILE_PATH" 2>&1 || true)
  fi
  if [[ -n "$LINT_OUT" ]]; then
    ERRORS+="=== Linter errors ===\n$LINT_OUT\n\n"
  fi

  # --- Tests ---
  if [[ -x "$VENV/bin/pytest" ]]; then
    TEST_OUT=$(cd "$PROJECT_ROOT" && "$VENV/bin/pytest" --tb=short -q 2>&1 || true)
    # Only report if there are failures (ignore "no tests ran")
    if echo "$TEST_OUT" | grep -qE "^(FAILED|ERROR|[0-9]+ failed)"; then
      ERRORS+="=== Test failures ===\n$TEST_OUT\n\n"
    fi
  fi
fi

# ---------- JS/TS ----------
if [[ "$LANG_TYPE" == "js" ]]; then
  LOCAL_BIN="$PROJECT_ROOT/node_modules/.bin"

  # --- Formatter (silent auto-fix) ---
  PRETTIER=""
  if [[ -x "$LOCAL_BIN/prettier" ]]; then
    PRETTIER="$LOCAL_BIN/prettier"
  elif command -v prettier &>/dev/null; then
    PRETTIER="prettier"
  fi
  if [[ -n "$PRETTIER" ]]; then
    "$PRETTIER" --write "$FILE_PATH" 2>/dev/null || true
  fi

  # --- Linter ---
  ESLINT=""
  if [[ -x "$LOCAL_BIN/eslint" ]]; then
    ESLINT="$LOCAL_BIN/eslint"
  elif command -v eslint &>/dev/null; then
    ESLINT="eslint"
  fi
  if [[ -n "$ESLINT" ]]; then
    LINT_OUT=$("$ESLINT" "$FILE_PATH" 2>&1 || true)
    # ESLint exits non-zero for errors/warnings; only capture if there's real output
    if [[ -n "$LINT_OUT" ]] && echo "$LINT_OUT" | grep -qE "(error|warning)"; then
      ERRORS+="=== ESLint ===\n$LINT_OUT\n\n"
    fi
  fi

  # --- Tests ---
  # Detect vitest vs jest
  JEST=""
  if [[ -f "$PROJECT_ROOT/vitest.config.ts" ]] || [[ -f "$PROJECT_ROOT/vitest.config.js" ]] || [[ -f "$PROJECT_ROOT/vitest.config.mjs" ]]; then
    if [[ -x "$LOCAL_BIN/vitest" ]]; then
      JEST="vitest_mode"
    fi
  fi
  if [[ -z "$JEST" ]]; then
    if [[ -x "$LOCAL_BIN/jest" ]]; then
      JEST="$LOCAL_BIN/jest"
    elif command -v jest &>/dev/null; then
      JEST="jest"
    fi
  fi

  if [[ "$JEST" == "vitest_mode" ]]; then
    TEST_OUT=$(cd "$PROJECT_ROOT" && "$LOCAL_BIN/vitest" run --reporter=verbose 2>&1 || true)
    if echo "$TEST_OUT" | grep -qE "(FAIL|× )"; then
      ERRORS+="=== Test failures ===\n$TEST_OUT\n\n"
    fi
  elif [[ -n "$JEST" ]]; then
    TEST_OUT=$(cd "$PROJECT_ROOT" && "$JEST" --findRelatedTests "$FILE_PATH" --passWithNoTests --no-coverage 2>&1 || true)
    if echo "$TEST_OUT" | grep -qE "(FAIL|Tests:.*failed)"; then
      ERRORS+="=== Test failures ===\n$TEST_OUT\n\n"
    fi
  fi
fi

# ---------- Report ----------
if [[ -n "$ERRORS" ]]; then
  printf "%b" "$ERRORS" >&2
  exit 2
fi

exit 0
