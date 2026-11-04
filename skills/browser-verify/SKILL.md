---
name: browser-verify
description: Use when checking a web UI change in a browser, when something looks wrong in Firefox, Safari or WebKit only, or before claiming a screen works in every browser. Real engines without taking over the owner's screen, proof in numbers and pictures.
---

# Browser verify

## 1. The project's facts

Read the "Browser and visual" section of `docs/agents/checks.md`: the launcher,
the screenshot command, the server to point it at, the slot wrapper for browser
runs. A missing section: say so, then launch as below. Run every browser
through the machine slot wrapper the project names.

## 2. Pick engines by the claim

A claim about one engine needs that engine; "works everywhere" needs all four:
Chromium, Firefox, WebKit and Safari. Layout and CSS changes get Chromium,
Firefox and Safari at the widths and themes the project names.

## 3. Launch real engines, out of the owner's way

- **Chromium**: Playwright's build, headless. For 2× pixels at full frame rate (video, frame
  timing), use a real window on a Retina display instead. Headless 2× reaches only about
  16 fps, and the page still reports DPR 1. The window keeps 60 fps behind the owner's apps
  with `--disable-backgrounding-occluded-windows --disable-renderer-backgrounding`, focus
  handed back as for Safari.
- **Firefox**: the installed Firefox through Playwright's BiDi channel,
  `firefox.launch({ channel: "moz-firefox" })`, headless. Playwright's own
  patched Firefox can fail on a new macOS with "Could not find profile folder",
  and it is not the Firefox users run.
- **WebKit** (Playwright): renders like Safari but has none of Safari's
  scrolling physics or settings. Use it for static layout only.
- **Safari**: Safari Technology Preview over its own `safaridriver`. Plain
  Safari refuses WebDriver while the owner has it open; the driver reports only
  a timeout. Setup, the focus hand-back and limits:
  [references/safari.md](references/safari.md).

Never take the owner's screen: headless where the engine allows it; otherwise
the window works behind their apps with focus handed back. Close every browser,
driver and dev server you started as soon as the check no longer needs it,
without asking: they are yours.

## 4. Wait for the page, not for time

A screenshot or reading is valid after all three:
- the page's own "rendered" signal (Storybook adds `sb-show-main` to `body`);
- a short settle for mounted content;
- every image in the viewport `complete` with a `naturalWidth`, then `decode()`d.

Safari paints lazy, async-decoded images late. A wait over an empty list of
images passes before content mounts, so the settle comes first.

## 5. Prove it

Done means numbers and a picture from each engine:
- computed values or geometry for what changed (`getComputedStyle`,
  bounding boxes, a pixel read from a canvas);
- one screenshot per engine, width and theme.

A difference with equal computed values is paint: isolate layers (hide a child,
sample pixels) and check assets before CSS. A decoder can drop an image's alpha
when its container metadata is off, and CSS gets the blame.

## 6. What no driver reaches

Elastic overscroll (rubber band) needs trackpad scroll phases. CDP gestures
produce it in Chromium only; WebDriver, Playwright WebKit and Firefox cannot.
Report it as unverified in those engines, or ask the owner for a manual check.

## 7. Report

Per engine: name and version, what was measured with its numbers, picture paths.
Then what stayed unverified and why.
