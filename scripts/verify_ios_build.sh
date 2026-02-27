#!/bin/bash
# ==============================================================================
# BibleAI — iOS Build Verification Gate
# ==============================================================================
# This script is the AUTOMATED PRE-MERGE GATE for all changes touching ios/.
# It must pass before any PR is merged into main.
#
# Usage:
#   ./scripts/verify_ios_build.sh
#
# Exit codes:
#   0 — Build succeeded, safe to merge
#   1 — Build failed, PR is blocked
#
# Orchestrator policy: NO PR touching ios/ may merge unless this script exits 0.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

PROJECT_PATH="$REPO_ROOT/ios/AppProject/BibleAI/BibleAI.xcodeproj"
SCHEME="BibleAI"
DESTINATION="platform=iOS Simulator,name=iPhone 17 Pro"

LOG_FILE="$REPO_ROOT/.build_verification.log"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=============================================="
echo " BibleAI iOS Build Verification Gate"
echo "=============================================="
echo ""

# ------------------------------------------------------------------------------
# Step 1: Validate project file exists
# ------------------------------------------------------------------------------
echo -n "→ Checking project file exists... "
if [ ! -d "$PROJECT_PATH" ]; then
    echo -e "${RED}FAIL${NC}"
    echo "  ERROR: Xcode project not found at: $PROJECT_PATH"
    exit 1
fi
echo -e "${GREEN}OK${NC}"

# ------------------------------------------------------------------------------
# Step 2: Validate no prohibited paths exist
# ------------------------------------------------------------------------------
echo -n "→ Checking prohibited paths... "
PROHIBITED_PATHS=(
    "$REPO_ROOT/ios/App"
    "$REPO_ROOT/ios/Sources/BibleTherapistCore/Views"
)
for prohibited in "${PROHIBITED_PATHS[@]}"; do
    if [ -e "$prohibited" ]; then
        echo -e "${RED}FAIL${NC}"
        echo "  ERROR: Prohibited path exists: $prohibited"
        echo "  See governance decision D014. This directory must not exist."
        exit 1
    fi
done
echo -e "${GREEN}OK${NC}"

# ------------------------------------------------------------------------------
# Step 3: Validate single @main entry point
# ------------------------------------------------------------------------------
echo -n "→ Checking for single @main entry point... "
MAIN_COUNT=$(grep -rl '@main' "$REPO_ROOT/ios/AppProject/" --include="*.swift" 2>/dev/null | wc -l | tr -d ' ')
if [ "$MAIN_COUNT" -eq 0 ]; then
    echo -e "${RED}FAIL${NC}"
    echo "  ERROR: No @main entry point found in ios/AppProject/"
    exit 1
elif [ "$MAIN_COUNT" -gt 1 ]; then
    echo -e "${RED}FAIL${NC}"
    echo "  ERROR: Multiple @main entry points found:"
    grep -rl '@main' "$REPO_ROOT/ios/AppProject/" --include="*.swift"
    exit 1
fi
echo -e "${GREEN}OK${NC}"

# ------------------------------------------------------------------------------
# Step 4: Validate no duplicate Swift filenames in app target
# ------------------------------------------------------------------------------
echo -n "→ Checking for duplicate Swift filenames... "
DUPES=$(find "$REPO_ROOT/ios/AppProject/BibleAI/BibleAI" -name "*.swift" -exec basename {} \; | sort | uniq -d)
if [ -n "$DUPES" ]; then
    echo -e "${RED}FAIL${NC}"
    echo "  ERROR: Duplicate Swift filenames found in app target:"
    echo "  $DUPES"
    exit 1
fi
echo -e "${GREEN}OK${NC}"

# ------------------------------------------------------------------------------
# Step 5: Clean build
# ------------------------------------------------------------------------------
echo ""
echo "→ Running xcodebuild clean build..."
echo "  Project:     $PROJECT_PATH"
echo "  Scheme:      $SCHEME"
echo "  Destination: $DESTINATION"
echo ""

if xcodebuild \
    -project "$PROJECT_PATH" \
    -scheme "$SCHEME" \
    -destination "$DESTINATION" \
    clean build \
    2>&1 | tee "$LOG_FILE" | tail -20; then

    # Check for BUILD SUCCEEDED in log
    if grep -q "BUILD SUCCEEDED" "$LOG_FILE"; then
        echo ""
        echo -e "${GREEN}=============================================="
        echo " ✓ BUILD VERIFICATION PASSED"
        echo "=============================================="
        echo -e " PR is cleared for merge.${NC}"
        rm -f "$LOG_FILE"
        exit 0
    fi
fi

echo ""
echo -e "${RED}=============================================="
echo " ✗ BUILD VERIFICATION FAILED"
echo "=============================================="
echo -e " PR is BLOCKED. See log: $LOG_FILE${NC}"
echo ""
echo -e "${YELLOW}Escalation protocol:${NC}"
echo "  1. iOS Engineer: debug and fix if the failure is in ios/"
echo "  2. If caused by package changes → escalate to owning agent"
echo "  3. File blocking issue in governance/TASKS.md"
exit 1