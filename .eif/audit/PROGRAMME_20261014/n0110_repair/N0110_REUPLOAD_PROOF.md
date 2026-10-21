# N-0110 repair: re-upload proof (clone of cip)

  [current_database()=cip_n0110p]
  [current_database()=cip_n0110p]
  [current_database()=cip_n0110p]
- alembic on clone: upgrade head, downgrade -1, upgrade head: ok
  [current_database()=cip_n0110p]
- before: fact rows 1823, units 6159, per customer {11: 1, 12: 3, 15: 688, 18: 2299, 20: 541, 52: 690, 57: 1522, 299: 415}
  [current_database()=cip_n0110p]
  [current_database()=cip_n0110p]
  [current_database()=cip_n0110p]
  first re-upload {"old_job": 965, "new_job": 1647, "status": "completed", "error": null}
  [current_database()=cip_n0110p]
  [current_database()=cip_n0110p]
  reason for job 1647: same week and product, now one row per site: +886 units (428 more rows); weeks the old load did not store: +0; old weeks not restated: +0. The old load read 1118 units from its resolved source rows and stored 151 (last row per key won).
  [current_database()=cip_n0110p]
- after first re-upload of job 965: fact rows 2251, units 7045, per customer {11: 1, 12: 3, 15: 1574, 18: 2299, 20: 541, 52: 690, 57: 1522, 299: 415}
  [current_database()=cip_n0110p]
  [current_database()=cip_n0110p]
  second re-upload {"old_job": 965, "new_job": 1648, "status": "completed", "error": null}
  [current_database()=cip_n0110p]
- after second re-upload of job 965: fact rows 2251, units 7045, per customer {11: 1, 12: 3, 15: 1574, 18: 2299, 20: 541, 52: 690, 57: 1522, 299: 415}
  difference customer 15: units 688 -> 1574 (+886), rows 362 -> 790
  second re-upload changed: nothing
  [current_database()=cip_n0110p]
  [current_database()=cip_n0110p]
  [current_database()=cip_n0110p]
  first re-upload {"old_job": 960, "new_job": 1649, "status": "completed", "error": null}
  [current_database()=cip_n0110p]
  [current_database()=cip_n0110p]
  reason for job 1649: same week and product, now one row per site: +0 units (0 more rows); weeks the old load did not store: +510; old weeks not restated: -510. The old load read 518 units from its resolved source rows and stored 510 (last row per key won).
  [current_database()=cip_n0110p]
- after first re-upload of job 960: fact rows 2251, units 7045, per customer {11: 1, 12: 3, 15: 1574, 18: 2299, 20: 541, 52: 690, 57: 1522, 299: 415}
  [current_database()=cip_n0110p]
  [current_database()=cip_n0110p]
  second re-upload {"old_job": 960, "new_job": 1650, "status": "completed", "error": null}
  [current_database()=cip_n0110p]
- after second re-upload of job 960: fact rows 2251, units 7045, per customer {11: 1, 12: 3, 15: 1574, 18: 2299, 20: 541, 52: 690, 57: 1522, 299: 415}
  second re-upload changed: nothing
  [current_database()=cip_n0110p]
  [current_database()=cip_n0110p]
  superseded by job 1647: from job 965, customer 15, rows 104, units 151, periods 7
  superseded by job 1649: from job 960, customer 18, rows 56, units 510, periods 1
- clone dropped. REUPLOAD_PROOF PASS
