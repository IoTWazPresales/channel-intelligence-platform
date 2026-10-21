# N-0111 baseline (before the build, tree 977985ba)

Observed in code and on cip (read only), from the N-0110 Part B finding and this session's reading:

- Customer sell-through apply upserted every figure from the incoming row: a sales-only reload set on-hand to empty for the same key, and
  cross-key supersession moved whole rows (units and stock together).
- A file with on-hand and no units column was refused (units_sold required).
- Week or month numbers without a year took the latest such week started by the receive date (a guess); 2-year-old files landed in the wrong year.
- No tenant week calendar: a week had a start date only when the customer's feed profile named one (Amazon and Pinnacle none).
- The stock chain compared each on-hand report with the previous one across any number of weeks without on-hand.
- Read model counted every day row as one observed week.
- Distributor (Pinnacle 29) path: sell-out and inventory are separate fact tables keyed by date (and invoice); no year guessing; no superseded table.
- cip: rev 20261015_0040; fact rows 3197, units 12394, on-hand 30832, superseded 390, positions 701, staging 46718.
