# Background Safari verification

Use the project's existing Safari launcher before building another. Real Safari
Technology Preview and system WKWebView are distinct targets; Playwright WebKit
covers static layout without a native window.

## Real Safari Technology Preview

The canonical real-STP route launches via `open -g -b` with
`-ApplePersistenceIgnoreState YES` under an exclusive lock, runs scripts over a
tokenized local bridge, places the window via Accessibility without raising it,
and captures that owned window. Gesture harnesses target the owned PID (not the
global input stream); the frontmost watcher aborts on activation while allowing
owner switches between other apps.

Inspect the installed tool's source and version first: older `repo-kit shoot`
versions open a WebDriver session then return focus best-effort (the
focus-handback path that stole focus in the November 2026 incident). Reuse the
verified background route while any replacement awaits native acceptance.

Keep the window visible behind the owner's windows (hiding/minimising stops
rendering) and leave pre-existing STP instances alone. Missing Accessibility or
Screen Recording permission is a setup dependency, never a reason to launch
foreground or open a permission prompt.

## System WebKit

A native WKWebView harness uses `.prohibited` activation policy with native and
process focus guards; report it as system WebKit, not Safari app acceptance.
Interactive recording modes are separate owner-driven operations.

## Acceptance of a replacement launcher

Prove routing, ownership, cleanup and focus-abort with mocked system calls and a
local HTTP fixture first — a source check or mocked pass never proves native
focus behavior. Native runtime acceptance verifies the frontmost trace across
launch, sizing, navigation, capture and cleanup plus viewport/cropping; an app
that activated and handed focus back failed. Never infer a runtime pass while
native launches are paused by the owner.
