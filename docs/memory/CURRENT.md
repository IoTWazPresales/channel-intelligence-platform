# CURRENT state

**Last updated:** 2026-08-10 (Evetech confirm + poll + CPOR activation flags)

**Branch:** `feat/p4-cst-six-customer-shapes` → **PR #26**

**Alembic on cip:** `20260808_0011` (head)

## Locked rules

- CST unmappable → Ignore → catalogue gaps (`source=cst`). Never auto-create PM.
- Game ≠ new structure_type — dual_header + wide-week unpivot.
- P5: live fetch now. **Listing↔CPOR activation** = point-in-time (obs price vs `cpor_case_line.srp`); statuses include **`no_case_detected`**. Persisted on `listing_observation.parse_flags.cpor_activation` (no migration). Not gated on ≥14d history.

## Proven

| Item | Proof |
|---|---|
| Takealot W31 | job **927** → **24** confirmed listings |
| Evetech Sales | job **925** → **44** confirmed via auto-finder `…/laptops-for-sale/{web_id}` (no Google) |
| Evetech poll | **44/44** HTTP 200 + JSON-LD prices (R6 999–R74 999) + activation flags |
| Takealot poll | **24/24** HTTP 200 but **SPA shell** — parse_failed (`price_noise_or_shell`); needs better fetch later |
| CPOR check | 58× `no_case_detected`, 10× `no_product_link` (no cases uploaded yet) |
| Amazon soak | 51 listings (prior) |
| Game W27 | job **928** → **565** staging / **6** periods |

**Folder:** `…\Retail\Client RAW Report\`

## Next

1. Upload latest CPOR → re-poll → prove `not_activated` / `price_consistent`
2. Takealot live HTML/API fetch (urllib gets Next.js shell only)
3. Promote PR #26 when Warren asks

**Env:** local Windows. `cip` @ `20260808_0011`. Listing flags on.
