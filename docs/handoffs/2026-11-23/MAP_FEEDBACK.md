# Warren's map revision brief ? latest feedback, carried forward 2026-11-23

**The shown MapLibre appearance is not approved. Provider selection is unanswered. No rollout or tenant setting write is authorized by a preselected approval option.**

## Requested outcome

1. Replace the disliked country-level grouping markers with a better visual matching the shipping-map icon/point language. Apply the same requirement to city/street and mall views.
2. Match the general page theme to the shipping map, as previously requested. A shared component import is not proof of visual parity: compare actual rendered pixels.
3. Keep pins and proposed pins, their data, selection/detail and confirmation controls in the **right-hand side panel**. Avoid the large proposed-pins list beneath the map and the resulting page scrolling. Use appropriate internal panel scrolling while preserving keyboard access and visible actions.
4. Warren requests removal of the prominent OpenStreetMap contributors label. Record the exact request; a compliant presentation must still retain required OSM/provider credits. A compact information/credit control, removal of duplicated credit text, or a short initially visible then dismissible/collapsible credit is a proposed alternative, not yet a user-approved design.

## Canonical shipping reference and current divergence

- `apps/web/src/features/supply-inbound/onTheWater/OnTheWater.tsx`, especially `ClusterMarker`, `MapPanel`, `MapCanvas`, `MapAside`.
- `apps/web/src/features/maps/MapMarker.tsx`: actual shipping default is a filled point/halo, not an assumed anchor/vessel pictogram.
- Store prototype already imports this marker, but passes proposed/hollow states, different colours, sizes and hit areas. All192coordinate points are proposals, producing many hollow/dashed red rings. Changing only the import cannot satisfy Warren's feedback.
- Reuse existing `ProposedPinsPanel` and parent handlers when relocating UI. Do not create another confirm writer or duplicate actions below and beside the map.

## Existing paths to preserve

| Trigger | API | Celery | Writer / model |
|---|---|---|---|
| View stores | GET `/api/v1/store-dc/map` | None for rendering | Existing map reader/proposal response |
| Read map configuration | GET `/api/v1/tenant-settings` | None | Existing tenant settings reader |
| Prototype switch/search/pan/zoom | None | None | Private browser/local state |
| Confirm one proposed location | POST `/api/v1/store-dc/pins/confirm` | None | `useProposalConfirm` -> canonical `confirm_pins` |
| Confirm several | POST `/api/v1/store-dc/pins/confirm-bulk` | None | Same canonical confirmation service |
| Existing manually entered pin | POST `/api/v1/store-dc/pins` | None | Existing `drop_pin` path |

This is a routing reference, not a completed fix-protocol commit-model audit. Before implementing a confirmation/writer change, inspect transaction boundaries and publish the full required audit. This requested visual/layout work should preserve those writers.

## Preview/data truth

The three images in `assets/` are **revision references**, not approved deliverables. They were rendered from real app data with an explicitly temporary browser-only GET settings response override. Actual tenant settings were empty before/after; prototype was restored off and contexts closed. No locations were saved.

Actual payload:310records/four customers,192proposed coordinate points, zero confirmed. Selected A02/Fourways is a proposed intersection near visible OSM Fourways Mall, not a verified retailer/building coordinate. A01/Clearwater Mall resolves to rural Clearwater at-28.65,23.98333, confidence0.7; review is BACKLOG-267 before bulk confirmation. Do not silently correct or confirm any proposal for appearance.

The preview provider was verified via normal Chromium reads: `https://tiles.openfreemap.org/planet` and `https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf`, attribution `OpenFreeMap`. It is still **not configured or approved for production**.

## Attribution sources checked

- https://osmfoundation.org/wiki/Licence/Attribution_Guidelines ? interactive map attribution remains required; the guidance permits specified dismiss/collapse patterns with discoverable licence information.
- https://openfreemap.org/ ? provider/schema/attribution information.

The request to remove a long strip does not require keeping that duplicated strip; complete removal of required attribution is not the proposed implementation. No legal/product implementation change was made during handoff.
