# Precision workbench design update

Implemented October 27, 2026 for the existing local React/FastAPI prototype.

The direction uses a dark navy navigation rail, a cobalt action color, white
operator surfaces, and a custom isometric assembly illustration. The setup screen
introduces the procedure, while the running workspace gives priority to the
current instruction, captured evidence, and next action. No external image/font
service or new frontend dependency was added.

## What changed

- Responsive navigation with a workspace anchor, a workflow guide, and contextual
  session history. The brand link preserves the running session.
- A split setup layout with original SVG artwork, PDF drag-and-drop, the existing
  file chooser, and a clear three-stage upload/review/inspection indicator.
- A native modal guide with keyboard dismissal and correct mock-mode limitations.
- Updated checklist review, reference/count chips, camera standby framing,
  result panels, status colors, and a compact map of actual server step statuses.
- An original shield favicon, restrained interaction transitions, and a checking
  indicator shown only during an actual pending check. Reduced motion is honored.
- Readable main instruction/result text, keyboard focus, and mobile navigation
  controls with explicit accessible names.

The review acknowledgment, server step locks, pass/override Continue hold,
provider disclosures, manual override provenance, and conservative uncertainty
behavior remain in place. The illustration is labeled as an illustration and
is never used as live inspection evidence.

## Verification

- 170 backend tests and 65 frontend tests passed; TypeScript and production build
  passed. The visual fixture also passed a separate TypeScript check.
- Browser verified: guide opens and Escape closes it; actual synthetic PDF upload
  reaches review; Start remains disabled before acknowledgment; acknowledgment
  opens inspection; session-history navigation opens the audit without changing
  the active task.
- Setup inspected at 1280, 768, and 390 CSS px without horizontal overflow.
- Nine synthetic result states with long instructions and 50 steps inspected at
  all three target widths: 27 scenarios, none with horizontal document overflow.
- Screenshots and the responsive log are retained in ignored
  `private_assets/design-v2/`. These are application checks, not real-model or
  physical-kit validation. Real camera/microphone and Meta gates remain pending.

The updated source bundle can be reproduced with:

```sh
.venv/bin/python -m scripts.package_source --output private_assets/stepguard-design-source.zip
```

Existing bundles are preserved; choose a new output filename for later revisions.
