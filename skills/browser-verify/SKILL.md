---
name: browser-verify
description: Use when checking a web UI change in a browser, when something looks wrong in Firefox, Safari or WebKit only, or before claiming a screen works in every browser. Real engines without taking over the owner's screen, proof in numbers and pictures.
---

# Browser verify

## 1. The project's facts

Read "Browser and visual" in `docs/agents/checks.md`: launcher, screenshot
command, target server, and slot wrapper. If missing, say so and launch as
below. Run every browser through the project's machine slot wrapper.

## 2. Pick engines by the claim

A single-engine claim needs that engine; "works everywhere" needs Chromium,
Firefox, WebKit and Safari. Layout and CSS changes get Chromium, Firefox and
Playwright WebKit at the project's widths and themes. Add real Safari for
Safari-specific behavior via the verified background route; identify system
WKWebView separately from the Safari application.

## 3. Launch real engines, out of the owner's way

- **Chromium**: Playwright headless. For 2× pixels at 60 fps (video, frame
  timing), use a real Retina window instead (headless 2× caps at ~16 fps and
  DPR 1) with `--disable-backgrounding-occluded-windows --disable-renderer-backgrounding`,
  a verified no-activation launcher, and a focus guard.
- **Firefox**: installed Firefox via Playwright BiDi,
  `firefox.launch({ channel: "moz-firefox" })`, headless (Playwright's patched
  build can fail on new macOS with "Could not find profile folder" and differs
  from user Firefox).
- **WebKit** (Playwright): static layout only; lacks Safari scrolling physics.
- **Safari**: project's focus-guarded background Safari Technology Preview
  harness — inspect its launch path first (`safaridriver` + focus handback is
  not the same route; see [references/safari.md](references/safari.md)).

Leave the owner's focus untouched: native routes launch without activation,
monitor frontmost state, and abort on activation (returning focus afterward is
recovery, not proof). Close only the browser, watcher and server owned by this run.

## 4. Wait for the page, not for time

Valid only after: the rendered signal (Storybook's `sb-show-main` on `body`),
a short mount settle (first, so an empty image list does not pass early), and
every viewport image `complete` with `naturalWidth` and `decode()`d (Safari
paints lazy images late).

## 5. Prove it

Done means numbers and a picture from each engine:
- computed values or geometry for what changed (`getComputedStyle`, bounding
  boxes, canvas pixel read);
- when driving parameterized URL `args=`, verify the resulting DOM state
  (`data-side`, `dir`, `data-variant`) since Storybook drops mistyped args silently;
- one screenshot per engine, width and theme.

A difference with equal computed values is paint: isolate layers (hide a child,
sample pixels) and check assets before CSS — a decoder can drop alpha when
container metadata is off.

## 6. What no driver reaches

Elastic overscroll (rubber band) needs trackpad scroll phases. CDP produces it
in Chromium only; WebDriver, Playwright WebKit and Firefox cannot. Report it as
unverified there, or ask the owner for a manual check.

## 7. Report

Per engine: name and version, measured numbers, picture paths. Then what stayed
unverified and why.
