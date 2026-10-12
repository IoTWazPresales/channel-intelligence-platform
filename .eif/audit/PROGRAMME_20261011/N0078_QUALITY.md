# N-0078 listing quality

2026-10-12. Signed in as Local Admin, dark theme, Market & Listings, tab Listing quality / SEO.

The page says checks use the last stored snapshot for Takealot and Evetech, a flag is amber and does not block, missing fields say No data, Amazon is not checked, and search position is deferred.

The grid columns are Listing, Retailer, Flags, Last check, Price and stock, Title, Images, Description, Key specs, Buy box, and Reviews. The first rows are Amazon and every check cell says No data.

Stored snapshots on cip were stamped with rules_version n0078-2026-10-12. No new fetch. Unit tests in tests/test_listing_quality.py passed (4, then 5 with the ledger balance test in the same run).

N-0076 and N-0085 are still proposed. This is not coverage of every retailer those nodes will add. Search terms were not supplied, so search position stays deferred. The grid does not yet show weekly sell-through.
