# Web UI test-audit checks

Browser and DOM examples for `test-audit` capability, adapter, assertion, and
global-leak classes:

- **Unexercised capability branches:** modern platform APIs (`CloseWatcher`,
  WAAPI `animate()`, `scroll-state`, `ResizeObserver`) that tests never
  exercise because the DOM emulator lacks them and only runs the fallback.
- **Duplicated test adapters:** multi-line mocks or harnesses
  (`ResizeObserver`, `matchMedia`, history/watcher fakes, store fixtures)
  copy-pasted across files with subtle drift instead of one contract-checked
  test adapter.
- **Silent or swallowed assertions:** smoke-only checks (`toBeTruthy()`,
  `not.toThrow()`), `console.error` spies that hide framework/hydration
  warnings, or assertions inside `if` guards or unawaited callbacks.
- **Order-dependent global leaks:** mutations to `window.history`,
  `document.body`, `localStorage`, module singletons, or fake timers without
  symmetric `afterEach` cleanup.
