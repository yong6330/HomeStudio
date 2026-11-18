# HomeStudio UI build (Stitch port)

Source of truth for the UI is the Google Stitch export (account/onboarding + dashboard, 13 screens).
`port_*.py` turn each Stitch `code.html` into `software/frontend/views/<screen>.html` with only these changes:
CDN/remote images removed (mascot/illustrations vendored in `frontend/assets/`, demo photos replaced by real
snapshot/thumbnail/clip data), inline Stitch demo scripts removed (behaviour lives in `frontend/app.js`),
`data-k` / `data-tpl` hooks added for data binding, and copy fixed where the demo text was untrue for HomeStudio
(e.g. "클라우드 저장" -> local storage, E2EE -> Tailscale, fake sensors -> "준비 중").

Rebuild CSS after editing views (Tailwind standalone CLI v3, Stitch `tailwind.config` verbatim):

    tailwindcss -c software/ui_build/tailwind.config.js -i software/ui_build/input.css -o software/frontend/app.css --minify

Runtime has no external dependencies (fonts: Inter/Plus Jakarta Sans latin subsets + Material Symbols subset, local).
