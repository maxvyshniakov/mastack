# Background Safari verification

Use the project’s existing Safari launcher before constructing another one. Real
Safari Technology Preview and a system WKWebView are distinct verification targets.
Playwright WebKit covers static layout without a native window.

## Real Safari Technology Preview

The canonical real-STP route starts the app with `open -g -b` and
`-ApplePersistenceIgnoreState YES`, under an exclusive lock. It evaluates page
scripts through a tokenized local bridge, places the window through Accessibility
without raising it, and captures that owned window. Gesture harnesses post events
to the owned PID, not the global input stream. Its frontmost watcher aborts on
activation; owner switches between other applications are allowed.

Check the installed tool’s source and version for this route. Older `repo-kit
shoot` versions use WebDriver session creation followed by best-effort app
activation; that path caused focus stealing during the November 2026 incident.
Do not assume a command named Safari uses the canonical harness. Reuse the
verified background route while a replacement is awaiting native acceptance.

Keep the window visible behind the owner's windows: hiding or minimising it
stops rendering. Leave a pre-existing STP instance alone. Missing Accessibility
or Screen Recording permission is a setup dependency, not a reason to switch to
a foreground launcher or open a permission prompt during verification.

## System WebKit

A native WKWebView harness can use `.prohibited` activation policy and both native
and process-level focus guards. Report it as system WebKit, not Safari application
acceptance. Interactive recording modes are separate owner-driven operations.

## Acceptance of a replacement launcher

First prove routing, ownership, cleanup and focus-abort behavior with mocked
system calls and a local HTTP fixture. A source check or mocked pass does not prove
native focus behavior. Native acceptance then checks the frontmost trace throughout
launch, sizing, navigation, capture and cleanup; it also verifies viewport dimensions
and screenshot cropping. An app activated and then handed focus back did not pass.
Do not infer a runtime pass while native launches are paused by the owner.
