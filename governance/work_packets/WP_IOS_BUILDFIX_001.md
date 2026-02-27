# Work Packet: IOS-BUILDFIX-001 — Fix Current Build Error & Establish Build Stewardship

## Goal
1. Fix the current build error in `BibleAIApp.swift` so the app compiles and runs in Simulator.
2. Establish the iOS Engineer as Build Guardian with the verification script operational.

## Owner
iOS Engineer (Lead)

## Branch / Worktree Name
agent/ios/buildfix-001

## Priority
IMMEDIATE — blocks all other iOS work

---

## Part 1: Fix Current Build Error

### Error
```
BibleAIApp.swift:
  Missing argument for parameter 'chatViewModel' in call
  'init(chatViewModel:)' declared here
```

### Root Cause
`BibleAIApp.swift` instantiates a view (likely `ContentView`) that requires a `ChatViewModel` parameter, but no instance is being passed.

### Required Fix

In `ios/AppProject/BibleAI/BibleAI/BibleAIApp.swift`, the `@main` struct must:

1. Create a `ChatViewModel` instance (as a `@StateObject`).
2. Pass it to the root view.

#### Expected fix pattern:

```swift
import SwiftUI
import BibleTherapistCore

@main
struct BibleAIApp: App {
    @StateObject private var chatViewModel = ChatViewModel()

    var body: some Scene {
        WindowGroup {
            ContentView(chatViewModel: chatViewModel)
        }
    }
}
```

**Important considerations:**
- Check `ContentView.swift` to confirm the exact initializer signature. It may expect `@ObservedObject var chatViewModel: ChatViewModel` or similar.
- If `ContentView` wraps `DisclaimerView` → `ChatView` flow, ensure the ViewModel is passed through or injected via `.environmentObject()`.
- If using `environmentObject` pattern instead:

```swift
@main
struct BibleAIApp: App {
    @StateObject private var chatViewModel = ChatViewModel()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(chatViewModel)
        }
    }
}
```

  In this case, `ContentView` must use `@EnvironmentObject var chatViewModel: ChatViewModel` and the `init(chatViewModel:)` initializer should be removed.

- **Choose ONE pattern** (direct injection or environment object) and apply consistently across all views that need the ViewModel. Direct injection (`init` parameter) is recommended for clarity.

### Acceptance Criteria (Part 1)
- [ ] `BibleAIApp.swift` compiles with no errors
- [ ] `ContentView` receives `ChatViewModel` correctly
- [ ] App launches in Simulator showing initial view (DisclaimerView or ChatView)
- [ ] `./scripts/verify_ios_build.sh` exits with code 0

---

## Part 2: Verify Full View Chain

After fixing the entry point, verify that the full view chain compiles and renders:

```
BibleAIApp → ContentView → DisclaimerView → ChatView
                                           → InputBar
                                           → MessageBubble
                                           → RiskInterruptView
                                           → PaywallView
```

For each view, check:
- [ ] No missing initializer arguments
- [ ] All `@ObservedObject` / `@EnvironmentObject` / `@Binding` properties are satisfied
- [ ] No references to deleted files (`BibleTherapistApp`, anything from old `ios/App/`)
- [ ] All `import BibleTherapistCore` statements resolve correctly

If any view has unsatisfied dependencies, fix them in this work packet.

---

## Part 3: Build Guardian Setup

1. **Copy `scripts/verify_ios_build.sh`** to the repo root `scripts/` directory.
2. **Make it executable:** `chmod +x scripts/verify_ios_build.sh`
3. **Run it** and confirm exit code 0.
4. **Commit the script** as part of this PR.

### Acceptance Criteria (Part 3)
- [ ] `scripts/verify_ios_build.sh` exists and is executable
- [ ] Script exits 0 on current codebase
- [ ] Script correctly catches: prohibited paths, multiple @main, duplicate filenames, build failures

---

## Scope (files allowed to change)
- `ios/AppProject/BibleAI/BibleAI/BibleAIApp.swift`
- `ios/AppProject/BibleAI/BibleAI/Views/*.swift` (any view needing init fixes)
- `scripts/verify_ios_build.sh` (new file)

## Do Not Create or Modify
- `ios/App/` (DELETED per D014 — do not recreate)
- `ios/Sources/BibleTherapistCore/Views/` (REMOVED per D014)
- `governance/INTERFACES.md` (locked)
- `governance/DECISIONS.md` (locked — orchestrator updates only)

## Dependencies
- `BibleTherapistCore` package must compile (Models, Networking, Store, ViewModels)
- `ChatViewModel` must have a no-argument initializer OR the app entry point must provide required dependencies

## Test / Run Commands
```bash
# Full build verification gate
./scripts/verify_ios_build.sh

# Quick build only (no structural checks)
xcodebuild -project ios/AppProject/BibleAI/BibleAI.xcodeproj \
  -scheme BibleAI \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' \
  clean build

# Run tests (package)
cd ios && swift test
```

## Notes / Risks
- `ChatViewModel` may depend on `APIClient`, `AuthStore`, or `SSEClient` — if these require configuration (base URL, tokens), provide sensible defaults or mock values for Simulator runs.
- If `ChatViewModel` has no no-argument `init()`, you may need to add one with default/mock dependencies for development builds.
- After this fix, ALL future PRs touching `ios/` must run the build gate script before merge (per Build Guardian policy).