# Platform Open Questions

Only unresolved items that materially affect future page-by-page work are listed.

1. What is the intended long-term port contract for native local mode (`8000` vs `8001`) given current script/docs combinations?
2. Which modules are expected to become production-critical first (for prioritizing depth and test investment): pricing, promotions, lineup, budgets, or others?
3. Should generic import processing remain primarily synchronous, or is there a planned migration timeline to broker-backed async for non-Product-Master templates?
4. What are the required production auth and role behaviors (beyond stub headers) that must shape upcoming page UX and API guards?
5. For market intelligence, what concrete external datasets/integrations are in scope so the page can move from static contract preview to operational module?
6. What is the target policy for retry/recovery observability dashboards for background jobs beyond per-job state endpoints?
