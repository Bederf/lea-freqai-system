#!/bin/bash
# Freqtrade Session Initialization Script
# Standard startup ritual for consistent session management
# Usage: ./init.sh [--skip-tests] [--skip-logs]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
FEATURE_LIST="$SCRIPT_DIR/feature_list.json"
PROGRESS_LOG="$SCRIPT_DIR/progress.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Parse arguments
SKIP_TESTS=false
SKIP_LOGS=false
for arg in "$@"; do
  case $arg in
    --skip-tests) SKIP_TESTS=true ;;
    --skip-logs) SKIP_LOGS=true ;;
  esac
done

# ============================================================================
# 1. Verify Environment
# ============================================================================
echo -e "${BLUE}[1/5] Verifying Environment${NC}"

if ! cd "$SCRIPT_DIR" 2>/dev/null; then
  echo -e "${RED}✗ Failed to change to project directory: $SCRIPT_DIR${NC}"
  exit 1
fi
echo -e "${GREEN}✓ Project directory: $SCRIPT_DIR${NC}"

# Check Python environment
if [ ! -d ".venv" ]; then
  echo -e "${RED}✗ Python virtual environment not found (.venv)${NC}"
  echo "  Run: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi
echo -e "${GREEN}✓ Virtual environment found${NC}"

# Activate venv
if [ -f ".venv/bin/activate" ]; then
  source .venv/bin/activate
  echo -e "${GREEN}✓ Virtual environment activated${NC}"
else
  echo -e "${RED}✗ Could not activate virtual environment${NC}"
  exit 1
fi

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo -e "${GREEN}✓ Python version: $PYTHON_VERSION${NC}"

# ============================================================================
# 2. Check Git Status
# ============================================================================
echo -e "${BLUE}[2/5] Checking Git Status${NC}"

if ! git rev-parse --git-dir > /dev/null 2>&1; then
  echo -e "${RED}✗ Not a git repository${NC}"
  exit 1
fi

BRANCH=$(git rev-parse --abbrev-ref HEAD)
UNCOMMITTED=$(git status --short | wc -l)
echo -e "${GREEN}✓ Branch: $BRANCH${NC}"

if [ "$UNCOMMITTED" -gt 0 ]; then
  echo -e "${YELLOW}⚠ Uncommitted changes: $UNCOMMITTED files${NC}"
  echo "  Changes:"
  git status --short | head -5
  if [ "$UNCOMMITTED" -gt 5 ]; then
    echo "  ... and $((UNCOMMITTED - 5)) more"
  fi
else
  echo -e "${GREEN}✓ Working tree clean${NC}"
fi

# ============================================================================
# 3. Load Feature List & Project State
# ============================================================================
echo -e "${BLUE}[3/5] Loading Project State${NC}"

if [ ! -f "$FEATURE_LIST" ]; then
  echo -e "${RED}✗ Feature list not found: $FEATURE_LIST${NC}"
  exit 1
fi
echo -e "${GREEN}✓ Feature list loaded${NC}"

# Extract key metrics from feature_list.json
TOTAL_FEATURES=$(python3 -c "import json; print(json.load(open('$FEATURE_LIST')).get('total_features', 0))" 2>/dev/null || echo "unknown")
PASSING_FEATURES=$(python3 -c "import json; features=json.load(open('$FEATURE_LIST')).get('features', []); print(sum(1 for f in features if f.get('status')=='passing'))" 2>/dev/null || echo "0")
IN_PROGRESS=$(python3 -c "import json; features=json.load(open('$FEATURE_LIST')).get('features', []); print(sum(1 for f in features if f.get('status')=='in_progress'))" 2>/dev/null || echo "0")

echo -e "${GREEN}✓ Total features: $TOTAL_FEATURES (Passing: $PASSING_FEATURES, In Progress: $IN_PROGRESS)${NC}"

# ============================================================================
# 4. Run Smoke Tests (if not skipped)
# ============================================================================
if [ "$SKIP_TESTS" = false ]; then
  echo -e "${BLUE}[4/5] Running Smoke Tests${NC}"

  # Test 1: Config validation
  if [ -f "config.json" ]; then
    if python3 -c "import json; json.load(open('config.json'))" 2>/dev/null; then
      echo -e "${GREEN}✓ config.json is valid JSON${NC}"
    else
      echo -e "${RED}✗ config.json syntax error${NC}"
    fi
  else
    echo -e "${YELLOW}⚠ config.json not found${NC}"
  fi

  # Test 2: Strategy syntax check
  STRATEGIES=$(ls user_data/strategies/*.py 2>/dev/null | grep -E "FinAgent|Lea|Diagnostic" || true)
  if [ -n "$STRATEGIES" ]; then
    SYNTAX_OK=true
    for strategy in $STRATEGIES; do
      if ! python3 -m py_compile "$strategy" 2>/dev/null; then
        echo -e "${RED}✗ Syntax error in $strategy${NC}"
        SYNTAX_OK=false
      fi
    done
    if [ "$SYNTAX_OK" = true ]; then
      echo -e "${GREEN}✓ All strategy files have valid syntax${NC}"
    fi
  fi

  # Test 3: Virtual environment dependencies
  if python3 -c "import freqtrade; import pandas; import numpy" 2>/dev/null; then
    echo -e "${GREEN}✓ Core dependencies available${NC}"
  else
    echo -e "${YELLOW}⚠ Missing dependencies - run: pip install -r requirements.txt${NC}"
  fi
else
  echo -e "${YELLOW}⊘ Smoke tests skipped${NC}"
fi

# ============================================================================
# 5. Log Session Start & Display Status
# ============================================================================
if [ "$SKIP_LOGS" = false ]; then
  echo -e "${BLUE}[5/5] Logging Session Start${NC}"

  # Create progress.log if it doesn't exist
  if [ ! -f "$PROGRESS_LOG" ]; then
    cat > "$PROGRESS_LOG" << 'EOF'
# Freqtrade Progress Log
# Tracks session-to-session work and feature progress
# Format: [YYYY-MM-DD HH:MM] [SESSION_ID] [FEATURE/STATUS] - Description

## Session History

EOF
  fi

  # Log session start
  SESSION_ID=$(date +%s)
  TIMESTAMP=$(date '+%Y-%m-%d %H:%M')
  cat >> "$PROGRESS_LOG" << EOF

[$TIMESTAMP] [SESSION_$SESSION_ID] [INIT] Session started on branch '$BRANCH' with $UNCOMMITTED uncommitted changes
EOF
  echo -e "${GREEN}✓ Session logged${NC}"
else
  echo -e "${YELLOW}⊘ Logging skipped${NC}"
fi

# ============================================================================
# Display Project Status Summary
# ============================================================================
echo ""
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  FREQTRADE PROJECT STATUS${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"

echo ""
echo -e "${YELLOW}Repository:${NC}"
echo "  Branch: $BRANCH"
echo "  Status: $([ "$UNCOMMITTED" -eq 0 ] && echo "Clean ✓" || echo "$UNCOMMITTED files modified ⚠")"

echo ""
echo -e "${YELLOW}Features:${NC}"
echo "  Total: $TOTAL_FEATURES"
echo "  Passing: $PASSING_FEATURES ✓"
echo "  In Progress: $IN_PROGRESS 🔄"

echo ""
echo -e "${YELLOW}Current Work:${NC}"

# Show in-progress features
IN_PROGRESS_FEATURES=$(python3 -c "
import json
features = json.load(open('$FEATURE_LIST')).get('features', [])
for f in features:
  if f.get('status') == 'in_progress':
    print(f\"  - {f['name']}\")
" 2>/dev/null)

if [ -n "$IN_PROGRESS_FEATURES" ]; then
  echo "$IN_PROGRESS_FEATURES"
else
  echo "  (No features currently in progress)"
fi

echo ""
echo -e "${YELLOW}Blockers:${NC}"
BLOCKERS=$(python3 -c "
import json
validation = json.load(open('$FEATURE_LIST')).get('validation_status', {})
blockers = validation.get('blockers', [])
if blockers:
  for b in blockers:
    print(f'  ⚠ {b}')
else:
  print('  (No blockers)')
" 2>/dev/null)
echo "$BLOCKERS"

echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo "  1. Review feature_list.json for current status"
echo "  2. Check progress.log for session history"
echo "  3. Select a failing feature to implement"
echo "  4. Run validation after changes"
echo ""
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo ""

echo -e "${GREEN}✓ Session initialization complete${NC}"
echo "  Ready to start work. Use 'run_validation.sh' after making changes."
