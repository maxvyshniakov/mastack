# Safari through Safari Technology Preview

## Why not Safari itself

`safaridriver` only drives a Safari it launched for automation. With the
owner's Safari open, `POST /session` times out after about 30 s; the reason
("Safari was not launched for automation") appears only in the system log:
`log show --last 1m --predicate 'process == "Safari"'`. Do not quit the
owner's Safari. Safari Technology Preview is a separate app with its own
driver, settings and engine build close to the shipping Safari.

## One-time setup, by the owner

- Install it: `brew install --cask safari-technology-preview`. The package
  installer asks for an administrator password, so the owner runs it.
- In Safari Technology Preview's own Settings: Advanced → "Show features for
  web developers", then Developer → "Allow remote automation". Safari's own
  setting does not carry over.
- Until then the driver answers: "You must enable 'Allow remote automation'".

## A session that leaves the owner alone

1. Start `/Applications/Safari Technology Preview.app/Contents/MacOS/safaridriver -p <free port>`,
   wait for `GET /status`.
2. Record the frontmost app's bundle id, create the session with
   `browserName: "Safari Technology Preview"`, then activate the recorded app
   again (JXA: `NSRunningApplication.activateWithOptions`). No permission
   prompt is involved.
3. The window now works behind the owner's apps: it keeps drawing frames
   (60 fps measured) and screenshots work.

4. After `DELETE /session`, quit the browser if this run started it. In
   automation mode it ignores real input, window close and a polite quit, so
   it stays open: force-terminate it
   (`NSRunningApplication.forceTerminate`). It holds no user data.

Keep it on screen. A hidden or minimised window makes the page
`visibilityState: "hidden"`: `requestAnimationFrame` stops and screenshots
fail. macOS clamps a window rect to the screen, so it cannot be parked off it.

## Limits

- WebDriver screenshots cover the viewport only.
- The window rect includes the toolbar. Set it, read `innerWidth` and
  `innerHeight`, and correct by the difference to get the viewport size.
- `webinspectord` cannot be restarted: System Integrity Protection.
