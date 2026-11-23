# MapLibre browser-only preview for Warren

2026-11-22. **Three useful rendered screenshots captured and visually inspected. Approval pending.**

- Country/store network: `preview-2/01-country-preview.png` — actual310store records,192proposed coordinate records,22visible clusters/two individual overlays in the captured overview.
- City: `preview-4/02-city-preview.png` — Fourways/Sandton/Midrand streets and place labels, using the actual selected MakroA02 proposal.
- Mall/street area: `preview-4/03-mall-area-proposed-preview.png` — visible OSM **Fourways Mall** building/label, surrounding roads and POIs. The proposed pin is at a road intersection nearby; this does not verify the retailer/store/building coordinate.

This used an explicitly authorized ephemeral browser GET-response override for `/api/v1/tenant-settings`, preserving the real empty settings and adding only verified public OpenFreeMap TileJSON/glyph/attribution values to the browser response. All store data and coordinates came from the actual application. No record, coordinate, provider setting or source file was changed; no pin was dragged/dropped/confirmed. Normal sign-in was the only permitted application mutation used.

Ordinary Chromium preflight reached official Liberty style200, actual TileJSON `https://tiles.openfreemap.org/planet`200 with all required OpenMapTiles layers, and actual `Noto Sans Regular/0-255` glyph200. Evidence `provider-browser-preflight-2/results.json`; first glyph probe remains invalid due to percent-encoded placeholder substitution, preserved separately. The root's earlier Python403 is a separate retained observation; no header/proxy/challenge changes were used here.

Actual preview2 and preview4 each exited0 with no authenticated console errors, page exceptions or blocked business writes, and all observed provider responses200. Actual rendered attribution includes OpenStreetMap/OpenFreeMap/OpenMapTiles. Each run disabled its response override, refetched real settings through normal browser GET200 and proved they remained `{}`, switched the prototype off, and closed the ephemeral context. See each phase's `results.json` and the `.exit.txt` files.

Failures/limits retained: preview1 failed a missing-await overlay-count harness assertion after rendering; cleanup succeeded. Preview3 stopped at an overly narrow urban-name selection filter, without inventing coordinates; cleanup succeeded. Preview2's first mall-named candidate MakroA01/Clearwater points at a rural Schmidtsdrif area and is unsuitable for mall-accuracy acceptance. That existing proposal mismatch was reported to the coordinator; it was not fixed or confirmed. Preview4 uses the exact observed A02/Fourways record and demonstrates useful urban and street visuals. All192coordinate records remain **proposed**, zero confirmed. No map rollout or production provider configuration has occurred.
