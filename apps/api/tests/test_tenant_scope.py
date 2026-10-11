"""A second tenant's ORM read must not return the first tenant's row."""

from __future__ import annotations

import logging

from sqlalchemy import String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.core.tenant_scope import (
    TENANT_CLASSES,
    install_tenant_select_scope,
    request_tenant_id,
    tenant_id_from_user,
)


class _Base(DeclarativeBase):
    pass


class _Owned(_Base):
    __tablename__ = "n0055_owned"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(32))


def test_second_tenant_cannot_read_first(caplog) -> None:
    install_tenant_select_scope()
    names = {cls.__name__ for cls in TENANT_CLASSES}
    assert {
        "DimProduct",
        "DimCustomer",
        "DimDistributor",
        "ImportJob",
        "CporCase",
        "FactSalesSellout",
        "FactInboundShipment",
    } <= names

    engine = create_engine("sqlite://")
    _Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, class_=Session)
    with SessionLocal() as session:
        session.add(_Owned(id=1, tenant_id="alpha", name="first"))
        session.add(_Owned(id=2, tenant_id="beta", name="second"))
        session.commit()

    TENANT_CLASSES.append(_Owned)
    token = request_tenant_id.set("beta")
    try:
        with SessionLocal() as session:
            with caplog.at_level(logging.DEBUG, logger="app.core.tenant_scope"):
                rows = session.scalars(select(_Owned).order_by(_Owned.id)).all()
            assert [row.name for row in rows] == ["second"]
            assert session.get(_Owned, 1) is None
            assert session.get(_Owned, 2) is not None
            assert tenant_id_from_user({"tenant_id": "beta"}) == "beta"
        request_tenant_id.reset(token)
        token = request_tenant_id.set("alpha")
        with SessionLocal() as session:
            rows = session.scalars(select(_Owned).order_by(_Owned.id)).all()
            assert [row.name for row in rows] == ["first"]
            assert session.get(_Owned, 2) is None
        request_tenant_id.reset(token)
        token = request_tenant_id.set("beta")
        with SessionLocal() as session:
            rows = session.scalars(select(_Owned).order_by(_Owned.id)).all()
            assert [row.name for row in rows] == ["second"]
    finally:
        request_tenant_id.reset(token)
        if _Owned in TENANT_CLASSES:
            TENANT_CLASSES.remove(_Owned)

    with SessionLocal() as session:
        rows = session.scalars(select(_Owned).order_by(_Owned.id)).all()
    assert [row.name for row in rows] == ["first", "second"]
