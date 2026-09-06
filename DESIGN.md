# Shared 0AL Design Language

Reference: SpecPM `landing_page/assets/specpm-design.css` and `viewer.css`,
revision `8a5ce3dece3d18bf8f601a5a599520bd520c7839`.

SpecSearch uses the same named color and type tokens, serif display hierarchy,
monospace metadata, square controls, thin rules and blue selection accent.
It keeps its compact discovery workspace rather than copying a marketing hero.
Status colors and selected states remain distinct from primary actions.

The CSS tokens are vendored, not loaded from a sibling checkout or remote CDN.
When the shared language changes, review these tokens alongside the SpecPM
reference and run desktop/mobile browser checks. A shared package can replace
this small copy when there is a versioned cross-project release process.

Instrument Serif, Inter and JetBrains Mono regular/variable fonts are self-hosted
from `google/fonts` (`ofl/instrumentserif`, `ofl/inter`, `ofl/jetbrainsmono`).
Their original SIL Open Font License notices are in `static/fonts`. No browser
request to Google Fonts is needed; the existing same-origin CSP is unchanged.
SpecPM-derived design tokens retain the MIT notice in `static/SPECPM-LICENSE`.

This change does not affect retrieval, verification, source membership or index
snapshots. SpecPM and SpecSpace source files are not modified.
