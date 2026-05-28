"""Import parsers (isolated from DB — pipeline handlers own persistence)."""

from app.services.imports.parsers.customer_sell_through_flat import ParseResult, parse_flat_report

__all__ = ["ParseResult", "parse_flat_report"]
