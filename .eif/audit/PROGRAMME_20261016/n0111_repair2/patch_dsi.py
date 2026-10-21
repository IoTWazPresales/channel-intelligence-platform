"""One-off patch for distributor_sales_inventory.py (N-0111 repair 2, D-0091 for repeated Pinnacle lines)."""

import pathlib

p = pathlib.Path("apps/api/app/services/imports/distributor_sales_inventory.py")
s = p.read_text(encoding="utf-8")


def sub(old: str, new: str) -> None:
    global s
    assert s.count(old) == 1, old[:90]
    s = s.replace(old, new)


# 1. pre-pass: build prefetch keys and the repeated-line groups from one place.
start = s.index("    # N-0111 (D-0110): a reload of the same invoice line keeps the figures it replaces.\n")
end = s.index("    for line in lines:\n        parts: list[str] = []\n")
s = (
    s[:start]
    + '''    # N-0111 (D-0110): a reload of the same invoice line keeps the figures it replaces.
    # N-0111 (D-0091): lines of this load that repeat a key are summed, or counted once when identical.
    from app.services.imports.dsi_line_supersede import (
        DUPLICATE,
        LEAD,
        RETURNS,
        SELLOUT,
        LineSupersede,
        RepeatedLines,
    )

    keeper = LineSupersede(db, job_id=int(job.id), tenant_id=tid)
    repeats = RepeatedLines()
    pre_keys: dict[str, list[str]] = {SELLOUT: [], RETURNS: []}
    for line in lines:
        target = _dsi_sale_target(line)
        if target is None:
            continue
        table, sk, figures = target
        pre_keys[table].append(sk)
        repeats.add(table, sk, line, figures)
    for table, keys in pre_keys.items():
        keeper.prefetch(table, keys)
'''
    + s[end:]
)

# 2. sell-out branch: only the first line of a key writes; the others point at its row.
start = s.index('                figures = {\n                    "units": qty_f,')
end = s.index('                parts.append("sellout")\n') + len('                parts.append("sellout")\n')
block = s[start:end]
new_block = '''                role = repeats.role(line.id)
                if role != LEAD:
                    # D-0091: the key is written once, from its first line.
                    line.fact_sellout_row_id = repeats.fact_id(SELLOUT, sk)
                    parts.append("duplicate" if role == DUPLICATE else "sellout")
                else:
                    figures = repeats.figures(SELLOUT, sk, {})
                    keeper.before_write(SELLOUT, sk, figures, line_id=int(line.id))
                    stmt = (
                        pg_insert(sell_tbl)
                        .values(
                            source_key=sk,
                            staging_line_id=int(line.id),
                            product_id=prod_id,
                            customer_id=cust_id,
                            distributor_id=dist_id,
                            channel_id=None,
                            period_start=tx,
                            transaction_date=tx,
                            invoice_no=inv_no,
                            units=figures["units"],
                            revenue=figures["revenue"],
                            unit_sellout_price_ex_tax_amount=figures["unit_sellout_price_ex_tax_amount"],
                            reported_revenue_amount=figures["reported_revenue_amount"],
                            computed_revenue_amount=figures["computed_revenue_amount"],
                            currency_code=figures["currency_code"],
                            source_import_job_id=job.id,
                            tenant_id=tid,
                        )
                        .on_conflict_do_update(
                            constraint="uq_fact_sales_sellout_source_key",
                            set_={
                                "staging_line_id": text("EXCLUDED.staging_line_id"),
                                "units": text("EXCLUDED.units"),
                                "revenue": text("EXCLUDED.revenue"),
                                "unit_sellout_price_ex_tax_amount": text(
                                    "EXCLUDED.unit_sellout_price_ex_tax_amount"
                                ),
                                "reported_revenue_amount": text("EXCLUDED.reported_revenue_amount"),
                                "computed_revenue_amount": text("EXCLUDED.computed_revenue_amount"),
                                "currency_code": text("EXCLUDED.currency_code"),
                                "source_import_job_id": text("EXCLUDED.source_import_job_id"),
                                "tenant_id": text("EXCLUDED.tenant_id"),
                                "updated_at": text("now()"),
                            },
                        )
                        .returning(sell_tbl.c.id)
                    )
                    rid = db.execute(stmt).scalar_one()
                    keeper.after_write(SELLOUT, sk, figures, fact_id=rid, line_id=int(line.id))
                    repeats.set_fact_id(SELLOUT, sk, int(rid) if rid is not None else None)
                    line.fact_sellout_row_id = int(rid) if rid is not None else None
                    applied_sell += 1
                    parts.append("sellout")
'''
s = s[:start] + new_block + s[end:]

# 3. returns branch.
start = s.index('                ret_figures = {"return_quantity": abs(qty_f), "unit_price": unit_px}\n')
end = s.index('                parts.append("return")\n') + len('                parts.append("return")\n')
new_block = '''                role = repeats.role(line.id)
                if role != LEAD:
                    parts.append("duplicate" if role == DUPLICATE else "return")
                else:
                    ret_figures = repeats.figures(RETURNS, sk, {})
                    keeper.before_write(RETURNS, sk, ret_figures, line_id=int(line.id))
                    ret_stmt = (
                        pg_insert(ret_tbl)
                        .values(
                            source_key=sk,
                            staging_line_id=int(line.id),
                            distributor_id=dist_id,
                            product_id=prod_id,
                            customer_id=cust_id,
                            transaction_date=tx,
                            invoice_no=inv_no,
                            return_quantity=ret_figures["return_quantity"],
                            unit_price=ret_figures["unit_price"],
                            import_job_id=job.id,
                        )
                        .on_conflict_do_update(
                            constraint="uq_fact_returns_source_key",
                            set_={
                                "return_quantity": text("EXCLUDED.return_quantity"),
                                "unit_price": text("EXCLUDED.unit_price"),
                                # N-0111: the stored row names the line and load that last set it.
                                "staging_line_id": text("EXCLUDED.staging_line_id"),
                                "import_job_id": text("EXCLUDED.import_job_id"),
                                "updated_at": text("now()"),
                            },
                        )
                        .returning(ret_tbl.c.id)
                    )
                    ret_id = db.execute(ret_stmt).scalar_one()
                    keeper.after_write(RETURNS, sk, ret_figures, fact_id=ret_id, line_id=int(line.id))
                    applied_ret += 1
                    parts.append("return")
'''
s = s[:start] + new_block + s[end:]

# 4. job summary.
sub(
    '''            "superseded_lines": keeper.recorded,
''',
    '''            "superseded_lines": keeper.recorded,
            # N-0111 (D-0091): repeated lines of this load that differed (summed) or were identical (counted once).
            "summed_lines": repeats.summed_lines,
            "duplicate_lines": repeats.duplicate_lines,
''',
)

# 5. the shared sale/return target helper, placed before the upsert function.
sub(
    "def upsert_dsi_facts_for_staging_job(db: Session, job: ImportJob) -> tuple[int, int, int, list[str]]:\n",
    '''def _dsi_sale_target(line: ImportDistributorSiStagingLine) -> tuple[str, str, dict[str, Any]] | None:
    """The fact a staged line writes a sale or return to: ``(table, source_key, figures)``, or None."""
    from app.services.imports.dsi_line_supersede import RETURNS, SELLOUT

    qty = float(line.quantity_sold) if line.quantity_sold is not None else None
    if not (line.resolved_distributor_id and line.resolved_product_id and line.resolved_customer_id):
        return None
    if line.transaction_date is None or qty is None or qty == 0:
        return None
    key = dict(
        distributor_id=int(line.resolved_distributor_id),
        customer_id=int(line.resolved_customer_id),
        product_id=int(line.resolved_product_id),
        transaction_date=line.transaction_date,
        invoice_no=_invoice_no_for_staging_line(line),
    )
    if qty > 0:
        eff = line.computed_revenue_amount
        if eff is None and line.reported_revenue_amount is not None:
            eff = line.reported_revenue_amount
        if eff is None:
            eff = 0.0
        return (
            SELLOUT,
            dsi_sellout_source_key(**key),
            {
                "units": qty,
                "revenue": float(eff),
                "unit_sellout_price_ex_tax_amount": line.unit_sellout_price_ex_tax_amount,
                "reported_revenue_amount": line.reported_revenue_amount,
                "computed_revenue_amount": line.computed_revenue_amount,
                "currency_code": line.currency_code,
            },
        )
    unit_px = line.unit_sellout_price_ex_tax_amount
    if unit_px is None and line.reported_revenue_amount is not None:
        unit_px = abs(float(line.reported_revenue_amount) / qty)
    return RETURNS, dsi_return_source_key(**key), {"return_quantity": abs(qty), "unit_price": unit_px}


def upsert_dsi_facts_for_staging_job(db: Session, job: ImportJob) -> tuple[int, int, int, list[str]]:
''',
)

p.write_text(s, encoding="utf-8")
print("patched")
