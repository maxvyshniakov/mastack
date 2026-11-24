# Web UI architecture checks

Browser and DOM examples for `architecture` Survey items 6 and 7:

- **Single-owner writes:** DOM attributes/styles, `window.history` vs
  `CloseWatcher`, focus management, scroll offset, CSS custom properties,
  `localStorage` / `sessionStorage`.
- **Leaked seams:** modules reaching across a component boundary via private
  DOM slots, `data-*` attributes, or internal CSS custom properties instead of
  an explicit interface or context.
- **Resource symmetry:** DOM event listeners, `ResizeObserver` /
  `IntersectionObserver` / `MutationObserver`, `requestAnimationFrame`, Web
  Animations, `CloseWatcher`, `AbortController` — every acquired handle must
  tear down symmetrically on unmount, re-entry, and mid-flight interruption.
- **Hot-path cost:** on scroll, resize, pointer, or animation paths, flag
  synchronous layout reads (`getBoundingClientRect`, `offsetHeight`),
  per-frame layout transitions (`height`, `width`), or O(N) DOM scans hidden
  behind a cheap-looking interface.
