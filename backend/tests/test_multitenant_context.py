"""Regresiones del contexto empresarial aplicado por SQLAlchemy."""

from unittest import TestCase

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.tenant_context import TenantContextError, set_tenant_context
from app.models.category import Category


class TenantContextTests(TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://", poolclass=StaticPool)
        Category.__table__.create(self.engine)
        self.db = Session(self.engine, expire_on_commit=False)

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_assigns_company_and_filters_reads(self) -> None:
        set_tenant_context(self.db, 1)
        first = Category(nombre="Ropa", estado=True)
        self.db.add(first)
        self.db.commit()

        set_tenant_context(self.db, 2)
        second = Category(nombre="Ropa", estado=True)
        self.db.add(second)
        self.db.commit()

        self.assertEqual(first.empresa_id, 1)
        self.assertEqual(second.empresa_id, 2)
        self.assertEqual(
            [row.id_categoria for row in self.db.scalars(select(Category))],
            [second.id_categoria],
        )

    def test_rejects_cross_company_write(self) -> None:
        set_tenant_context(self.db, 1)
        self.db.add(Category(nombre="Cruzada", estado=True, empresa_id=2))
        with self.assertRaises(TenantContextError):
            self.db.flush()

    def test_superadmin_reads_globally_but_must_select_company_to_write(self) -> None:
        set_tenant_context(self.db, 1)
        self.db.add(Category(nombre="Uno", estado=True))
        self.db.commit()
        set_tenant_context(self.db, 2)
        self.db.add(Category(nombre="Dos", estado=True))
        self.db.commit()

        set_tenant_context(self.db, None, is_superadmin=True)
        self.assertEqual(len(self.db.scalars(select(Category)).all()), 2)
        self.db.add(Category(nombre="Sin empresa", estado=True))
        with self.assertRaises(TenantContextError):
            self.db.flush()
