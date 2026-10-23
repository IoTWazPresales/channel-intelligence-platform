"""N-0115: data model and one query compiler under the dashboard builder (v2 queries).

loader (model file) -> graph (derived breakdowns, walls, validation) -> compiler (SQLAlchemy
Core) -> calc (null rules, totals) -> execute (request AsyncSession, cache) -> explain.
v1 (/query/execute and every stored widget, saved report and schedule) does not use this package.
"""
