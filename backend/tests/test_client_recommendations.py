"""CU26: pruebas del recomendador sobre SQLite en memoria, sin tocar PostgreSQL."""

import asyncio
import json
from datetime import datetime, time, timedelta
from decimal import Decimal
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from sqlalchemy import create_engine, event
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database import get_db
from app.models.branch import Branch
from app.models.branch_inventory import BranchInventory
from app.models.cart import Cart
from app.models.cart_detail import CartDetail
from app.models.category import Category
from app.models.city import City
from app.models.client import Client
from app.models.collection import Collection
from app.models.color import Color
from app.models.product import Product
from app.models.product_collection import ProductCollection
from app.models.product_image import ProductImage
from app.models.product_variant import ProductVariant
from app.models.promotion import Promotion
from app.models.promotion_product import PromotionProduct
from app.models.reservation import Reservation
from app.models.reservation_detail import ReservationDetail
from app.models.sale import Sale
from app.models.sale_detail import SaleDetail
from app.models.season import Season
from app.models.size import Size
from app.repositories.client_recommendations import ClientRecommendationsRepository
from app.routers import client_recommendations as routes
from app.routers.client_reservations import require_client
from app.services.catalog import (
    CatalogReferenceInactiveError,
    CatalogReferenceNotFoundError,
)
from app.services.client_recommendations import (
    ClientRecommendationsService,
    RecommendationAccessError,
)


NOW = datetime(2026, 9, 18, 12, 0, 0)

MODELS = (
    City, Branch, Category, Size, Color, Season, Collection, Client,
    Product, ProductVariant, ProductImage, ProductCollection,
    BranchInventory, Promotion, PromotionProduct,
    Cart, CartDetail, Reservation, ReservationDetail, Sale, SaleDetail,
)


ROUTE = "/api/client/recommendations"


def request(app, query="", token=True):
    messages = []
    path, _, query = f"{ROUTE}{query}".partition("?")

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": "GET", "scheme": "http", "path": path,
        "raw_path": path.encode(), "query_string": query.encode(),
        "root_path": "", "server": ("test", 80), "client": ("test", 1),
        "headers": [(b"authorization", b"Bearer fake")] if token else [],
    }
    asyncio.run(app(scope, receive, send))
    status = next(
        m["status"] for m in messages if m["type"] == "http.response.start"
    )
    body = b"".join(
        m.get("body", b"") for m in messages if m["type"] == "http.response.body"
    )
    return status, json.loads(body)


class RecommendationFixture(TestCase):
    """Catalogo minimo con historial real para el cliente 1 (usuario 10)."""

    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        for model in MODELS:
            model.__table__.create(self.engine)
        self.db = Session(self.engine, autoflush=False)
        self._seed()
        self.service = ClientRecommendationsService(self.db)
        self.app = FastAPI()
        self.app.include_router(routes.router)
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.app.dependency_overrides[require_client] = lambda: NS(
            id_usuario=10, rol="CLIENTE"
        )

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _seed(self):
        add = self.db.add
        add(City(id_ciudad=1, nombre="La Paz", estado=True))
        add(City(id_ciudad=2, nombre="Santa Cruz", estado=True))
        add(Branch(
            id_sucursal=1, id_ciudad=1, nombre="Centro", direccion="Av 1",
            hora_apertura=time(9, 0), hora_cierre=time(20, 0), estado=True,
        ))
        add(Branch(
            id_sucursal=2, id_ciudad=2, nombre="Norte", direccion="Av 2",
            hora_apertura=time(9, 0), hora_cierre=time(20, 0), estado=True,
        ))
        # 1 Poleras (categoria habitual), 2 Pantalones, 3 Abrigos
        for cid, nombre in ((1, "Poleras"), (2, "Pantalones"), (3, "Abrigos")):
            add(Category(id_categoria=cid, nombre=nombre, estado=True))
        for sid, nombre in ((1, "S"), (2, "M"), (3, "L")):
            add(Size(id_talla=sid, nombre=nombre, estado=True))
        for cid, nombre in ((1, "Negro"), (2, "Rojo"), (3, "Azul")):
            add(Color(id_color=cid, nombre=nombre, estado=True))
        add(Season(
            id_temporada=1, nombre="Invierno 2026", estado=True,
            fecha_inicio=NOW.date() - timedelta(days=30),
            fecha_fin=NOW.date() + timedelta(days=30),
        ))
        add(Collection(id_coleccion=1, nombre="Urbano", estado=True))
        add(Client(id_cliente=1, id_usuario=10))
        add(Client(id_cliente=2, id_usuario=20))  # cliente nuevo, sin historial

        # id 1..4 activos con stock; 5 sin stock; 6 inactivo.
        products = (
            (1, 1, "Polera basica", "UNISEX", 1, "100.00"),
            (2, 1, "Polera estampada", "UNISEX", 1, "120.00"),
            (3, 2, "Pantalon recto", "UNISEX", None, "200.00"),
            (4, 3, "Abrigo largo", "UNISEX", 1, "400.00"),
            (5, 1, "Polera agotada", "UNISEX", 1, "110.00"),
            (6, 1, "Polera retirada", "UNISEX", 1, "115.00"),
        )
        for pid, cat, nombre, seccion, temporada, precio in products:
            add(Product(
                id_producto=pid, id_categoria=cat, nombre=nombre,
                seccion=seccion, id_temporada=temporada,
                descripcion=f"Descripcion de {nombre}",
                precio=Decimal(precio), estado=pid != 6,
                created_at=NOW - timedelta(days=10 * pid),
                updated_at=NOW,
            ))
            add(ProductImage(
                id_imagen_producto=pid, id_producto=pid,
                url_imagen=f"https://cdn.test/{pid}.jpg", es_principal=True,
                created_at=NOW,
            ))
        add(ProductCollection(
            id_producto_coleccion=1, id_producto=1, id_coleccion=1
        ))

        # Variantes: producto 1 en talla M (habitual) y talla S.
        variants = (
            (1, 1, 2, 1, "P1-M-NEG", True),
            (2, 1, 1, 1, "P1-S-NEG", True),
            (3, 2, 2, 1, "P2-M-NEG", True),
            (4, 3, 3, 3, "P3-L-AZU", True),
            (5, 4, 2, 2, "P4-M-ROJ", True),
            (6, 5, 2, 1, "P5-M-NEG", True),
            (7, 6, 2, 1, "P6-M-NEG", True),
        )
        for vid, pid, talla, color, sku, estado in variants:
            add(ProductVariant(
                id_variante_producto=vid, id_producto=pid, id_talla=talla,
                id_color=color, sku=sku, estado=estado,
                created_at=NOW, updated_at=NOW,
            ))
        # Stock en sucursal 1 salvo la variante 6 (producto 5, agotado).
        stock = (
            (1, 1, 1, 10, 0), (2, 1, 2, 5, 0), (3, 1, 3, 8, 0),
            (4, 1, 4, 4, 0), (5, 1, 5, 6, 0),
            (6, 1, 6, 3, 3),   # todo reservado -> sin disponible
            (7, 1, 7, 9, 0),   # producto inactivo, pero con stock
            (8, 2, 3, 7, 0),   # producto 2 tambien en sucursal 2 / ciudad 2
        )
        for iid, branch, variant, actual, reservado in stock:
            add(BranchInventory(
                id_inventario_sucursal=iid, id_sucursal=branch,
                id_variante_producto=variant, stock_actual=actual,
                stock_reservado=reservado, stock_minimo=0,
                created_at=NOW, updated_at=NOW,
            ))

        add(Promotion(
            id_promocion=1, nombre="Invierno", codigo="INV", tipo_descuento="PORCENTAJE",
            valor=Decimal("10.00"), fecha_inicio=NOW - timedelta(days=5),
            fecha_fin=NOW + timedelta(days=5), acumulable=False, estado=True,
            created_at=NOW, updated_at=NOW,
        ))
        add(Promotion(
            id_promocion=2, nombre="Fijo", codigo="FIJO", tipo_descuento="MONTO_FIJO",
            valor=Decimal("30.00"), fecha_inicio=NOW - timedelta(days=5),
            fecha_fin=NOW + timedelta(days=5), acumulable=False, estado=True,
            created_at=NOW, updated_at=NOW,
        ))
        add(Promotion(
            id_promocion=3, nombre="Vencida", codigo="OLD", tipo_descuento="PORCENTAJE",
            valor=Decimal("90.00"), fecha_inicio=NOW - timedelta(days=40),
            fecha_fin=NOW - timedelta(days=20), acumulable=False, estado=True,
            created_at=NOW, updated_at=NOW,
        ))
        # Producto 4 con dos promociones vigentes y una vencida.
        for ppid, promo, product in ((1, 1, 4), (2, 2, 4), (3, 3, 4)):
            add(PromotionProduct(
                id_promocion_producto=ppid, id_promocion=promo, id_producto=product
            ))
        self.db.commit()

    # ------------------------------------------------------------------ helpers

    def _purchase(self, sale_id, client_id, variant_id, days_ago=5, quantity=1):
        self.db.add(Sale(
            id_venta=sale_id, id_sucursal=1, id_cliente=client_id,
            canal="DIGITAL", moneda="BOB", numero_venta=f"VTA-{sale_id}",
            estado="COMPLETADA", subtotal=Decimal("100.00"),
            descuento_total=Decimal("0.00"), total=Decimal("100.00"),
            fecha_venta=NOW - timedelta(days=days_ago),
            fecha_completada=NOW - timedelta(days=days_ago),
            created_at=NOW - timedelta(days=days_ago), updated_at=NOW,
        ))
        self.db.add(SaleDetail(
            id_detalle_venta=sale_id, id_venta=sale_id,
            id_variante_producto=variant_id, cantidad=quantity,
            precio_unitario=Decimal("100.00"), descuento_unitario=Decimal("0.00"),
            subtotal_linea=Decimal("100.00") * quantity,
        ))
        self.db.commit()

    def _cart(self, cart_id, client_id, variant_id, estado="ACTIVO"):
        self.db.add(Cart(
            id_carrito=cart_id, id_cliente=client_id, estado=estado,
            created_at=NOW - timedelta(days=1), updated_at=NOW - timedelta(days=1),
        ))
        self.db.add(CartDetail(
            id_detalle_carrito=cart_id, id_carrito=cart_id,
            id_variante_producto=variant_id, cantidad=1,
        ))
        self.db.commit()

    def _reservation(self, res_id, client_id, variant_id, estado="ATENDIDA"):
        self.db.add(Reservation(
            id_reserva=res_id, id_cliente=client_id, id_sucursal=1,
            codigo=f"RES-{res_id}", estado=estado,
            fecha_expiracion=NOW + timedelta(days=2),
            fecha_atencion_programada=NOW + timedelta(days=1),
            created_at=NOW - timedelta(days=3), updated_at=NOW,
        ))
        self.db.add(ReservationDetail(
            id_detalle_reserva=res_id, id_reserva=res_id,
            id_variante_producto=variant_id, cantidad=1,
            precio_unitario=Decimal("100.00"),
        ))
        self.db.commit()

    def recommend(self, user_id=10, **kwargs):
        kwargs.setdefault("now", NOW)
        return self.service.recommend(user_id, **kwargs)


class ProfileAndScoringTests(RecommendationFixture):
    def test_client_with_history_is_personalized_and_led_by_purchases(self):
        # Compra de la variante 1 -> producto 1, categoria Poleras, talla M.
        self._purchase(1, 1, variant_id=1, quantity=2)
        items, origen = self.recommend()

        self.assertEqual(origen, "PERSONALIZADO")
        self.assertTrue(items)
        # La otra polera (categoria afin, talla M) debe encabezar el ranking.
        self.assertEqual(items[0].id_producto, 2)
        self.assertEqual(items[0].motivo, "Basado en tus compras")
        # Lo ya comprado se relega al final.
        self.assertTrue(items[-1].ya_comprado)
        self.assertEqual(items[-1].id_producto, 1)

    def test_purchase_outweighs_cart_for_the_same_evidence(self):
        """Misma prenda como compra (cliente 1) vs carrito (cliente 2)."""
        self._purchase(1, 1, variant_id=1)
        self._cart(1, 2, variant_id=1)

        buyer_profile = self.service._build_profile(1, now=NOW)
        carter_profile = self.service._build_profile(2, now=NOW)
        buyer, _ = self.recommend(10)
        carter, _ = self.recommend(20)

        self.assertEqual(buyer_profile.comprados, {1})
        self.assertEqual(carter_profile.comprados, set())
        # Ambos perfiles normalizan a 1.0, pero solo la compra excluye y el
        # peso crudo de la compra es mayor: se verifica en el peso sin normalizar.
        self.assertGreater(
            self.service._decay(5) * 5.0, self.service._decay(1) * 1.5
        )
        # Para el comprador, el producto 1 queda relegado; para el del carrito no.
        self.assertEqual(buyer[-1].id_producto, 1)
        self.assertIn(1, [item.id_producto for item in carter])
        self.assertFalse(any(item.ya_comprado for item in carter))

    def test_purchased_category_outranks_carted_category(self):
        """Prueba decisiva: compra en Poleras vs carrito en Abrigos."""
        self._purchase(1, 1, variant_id=1)                  # producto 1, Poleras
        self._cart(1, 1, variant_id=5)                      # producto 4, Abrigos
        profile = self.service._build_profile(1, now=NOW)

        # La categoria comprada domina el perfil normalizado.
        self.assertEqual(profile.categorias[1], 1.0)
        self.assertLess(profile.categorias[3], profile.categorias[1])

        items, _ = self.recommend()
        by_id = {item.id_producto: item for item in items}
        # Otra polera (categoria comprada) por encima del abrigo del carrito,
        # aunque el abrigo tenga promocion vigente.
        self.assertGreater(by_id[2].score, by_id[4].score)
        self.assertEqual(by_id[2].motivo, "Basado en tus compras")

    def test_source_weights_are_ordered_purchase_reservation_cart(self):
        from app.services.client_recommendations import SOURCE_WEIGHTS

        self.assertGreater(SOURCE_WEIGHTS["COMPRA"], SOURCE_WEIGHTS["RESERVA"])
        self.assertGreater(SOURCE_WEIGHTS["RESERVA"], SOURCE_WEIGHTS["CARRITO"])
        self.assertGreater(
            SOURCE_WEIGHTS["CARRITO"], SOURCE_WEIGHTS["CARRITO_ABANDONADO"]
        )

    def test_reservation_and_abandoned_cart_feed_the_profile(self):
        self._reservation(1, 1, variant_id=4)        # producto 3, Pantalones
        self._cart(1, 1, variant_id=5, estado="ABANDONADO")  # producto 4, Abrigos
        profile = self.service._build_profile(1, now=NOW)

        self.assertIn(2, profile.categorias)   # Pantalones por la reserva
        self.assertIn(3, profile.categorias)   # Abrigos por el carrito abandonado
        # La reserva pesa mas que el carrito abandonado.
        self.assertGreater(profile.categorias[2], profile.categorias[3])

    def test_cancelled_reservation_and_pending_sale_are_ignored(self):
        self._reservation(1, 1, variant_id=4, estado="CANCELADA")
        self.db.add(Sale(
            id_venta=9, id_sucursal=1, id_cliente=1, canal="DIGITAL",
            moneda="BOB", numero_venta="VTA-9", estado="PENDIENTE",
            subtotal=Decimal("100.00"), descuento_total=Decimal("0.00"),
            total=Decimal("100.00"), fecha_venta=NOW - timedelta(days=1),
            created_at=NOW - timedelta(days=1), updated_at=NOW,
        ))
        self.db.add(SaleDetail(
            id_detalle_venta=9, id_venta=9, id_variante_producto=5, cantidad=1,
            precio_unitario=Decimal("100.00"), descuento_unitario=Decimal("0.00"),
            subtotal_linea=Decimal("100.00"),
        ))
        self.db.commit()

        profile = self.service._build_profile(1, now=NOW)
        self.assertTrue(profile.vacio)
        self.assertEqual(self.recommend()[1], "FALLBACK")

    def test_habitual_size_and_color_rank_and_pick_the_variant(self):
        # Compra talla M color Negro (variante 1, producto 1).
        self._purchase(1, 1, variant_id=1)
        items, _ = self.recommend()
        by_id = {item.id_producto: item for item in items}

        # El producto 1 tiene variantes M y S: debe sugerir la M habitual.
        self.assertEqual(by_id[1].variante_sugerida.talla, "M")
        self.assertEqual(by_id[1].variante_sugerida.id_variante_producto, 1)
        # El pantalon (talla L, color Azul) no recibe bono de talla/color.
        polera = by_id[2]
        pantalon = by_id[3]
        self.assertEqual(polera.variante_sugerida.talla, "M")
        self.assertEqual(pantalon.variante_sugerida.talla, "L")
        self.assertGreater(polera.score, pantalon.score)

    def test_size_term_breaks_the_tie_between_equal_products(self):
        """Dos prendas de la misma categoria, solo cambia la talla disponible."""
        self._purchase(1, 1, variant_id=1)  # talla M habitual
        # El producto 5 estaba agotado: se le habilita stock en talla S.
        self.db.get(BranchInventory, 6).stock_reservado = 0
        self.db.commit()
        self.db.get(ProductVariant, 6).id_talla = 1  # talla S
        self.db.commit()

        items, _ = self.recommend()
        by_id = {item.id_producto: item for item in items}
        # Producto 2 (talla M) sobre producto 5 (talla S), misma categoria.
        self.assertGreater(by_id[2].score, by_id[5].score)
        self.assertEqual(by_id[2].motivo, "Basado en tus compras")

    def test_decay_reduces_the_weight_of_old_signals(self):
        self.assertEqual(self.service._decay(10), 1.0)
        self.assertEqual(self.service._decay(60), 0.7)
        self.assertEqual(self.service._decay(120), 0.45)
        self.assertEqual(self.service._decay(400), 0.25)

    def test_bulk_quantity_is_capped(self):
        self._purchase(1, 1, variant_id=1, quantity=999)
        self._purchase(2, 1, variant_id=4, quantity=5)
        profile = self.service._build_profile(1, now=NOW)
        # Con el tope de unidades, 999 y 5 pesan igual: ninguna categoria domina.
        self.assertEqual(profile.categorias[1], profile.categorias[2])


class FiltersAndFallbackTests(RecommendationFixture):
    def test_out_of_stock_product_is_never_recommended(self):
        items, _ = self.recommend()
        self.assertNotIn(5, [item.id_producto for item in items])

    def test_inactive_product_is_never_recommended(self):
        items, _ = self.recommend()
        self.assertNotIn(6, [item.id_producto for item in items])

    def test_inactive_variant_is_not_offered_as_suggestion(self):
        self.db.get(ProductVariant, 1).estado = False  # talla M del producto 1
        self.db.commit()
        items, _ = self.recommend()
        by_id = {item.id_producto: item for item in items}
        self.assertEqual(by_id[1].variante_sugerida.talla, "S")

    def test_new_client_uses_fallback_with_available_products(self):
        # Popularidad generada por el cliente 1 para que el fallback ordene.
        self._purchase(1, 1, variant_id=5, quantity=4)  # producto 4
        items, origen = self.recommend(20)

        self.assertEqual(origen, "FALLBACK")
        self.assertTrue(items)
        self.assertFalse(any(item.ya_comprado for item in items))
        self.assertTrue(all(
            item.variante_sugerida.stock_disponible > 0 for item in items
        ))
        self.assertNotIn(5, [item.id_producto for item in items])
        self.assertNotIn(6, [item.id_producto for item in items])
        self.assertIn(items[0].motivo, {
            "Popular entre clientes similares", "En promocion vigente",
            "De la temporada y coleccion actual", "Novedad del catalogo",
            "Disponible para ti ahora",
        })

    def test_fallback_prefers_popular_over_merely_recent(self):
        self._purchase(1, 1, variant_id=4, quantity=5)  # producto 3, el mas vendido
        items, origen = self.recommend(20)
        self.assertEqual(origen, "FALLBACK")
        self.assertEqual(items[0].id_producto, 3)
        self.assertEqual(items[0].motivo, "Popular entre clientes similares")

    def test_limit_caps_the_number_of_recommendations(self):
        self._purchase(1, 1, variant_id=1)
        self.assertEqual(len(self.recommend(limit=2)[0]), 2)
        self.assertEqual(len(self.recommend(limit=1)[0]), 1)
        # Con 4 productos publicables, un limite mayor no inventa filas.
        self.assertEqual(len(self.recommend(limit=50)[0]), 4)

    def test_branch_and_city_scope_the_availability(self):
        # Solo el producto 2 tiene stock en la sucursal 2 / ciudad 2.
        items, _ = self.recommend(branch_id=2)
        self.assertEqual([item.id_producto for item in items], [2])
        items, _ = self.recommend(city_id=2)
        self.assertEqual([item.id_producto for item in items], [2])
        self.assertEqual(items[0].variante_sugerida.stock_disponible, 7)

    def test_unknown_or_inactive_branch_is_rejected(self):
        with self.assertRaises(CatalogReferenceNotFoundError):
            self.recommend(branch_id=999)
        self.db.get(Branch, 1).estado = False
        self.db.commit()
        with self.assertRaises(CatalogReferenceInactiveError):
            self.recommend(branch_id=1)

    def test_missing_client_profile_is_rejected(self):
        with self.assertRaises(RecommendationAccessError):
            self.recommend(user_id=999)


class PromotionAndPresentationTests(RecommendationFixture):
    def test_best_current_promotion_wins_and_expired_one_is_ignored(self):
        items, _ = self.recommend(20)
        abrigo = next(item for item in items if item.id_producto == 4)

        # Precio 400: 10% -> 360, monto fijo 30 -> 370. Gana el porcentaje.
        self.assertTrue(abrigo.tiene_promocion)
        self.assertEqual(abrigo.promocion.id_promocion, 1)
        self.assertEqual(abrigo.precio_base, Decimal("400.00"))
        self.assertEqual(abrigo.precio_final, Decimal("360.00"))
        self.assertEqual(abrigo.monto_descuento, Decimal("40.00"))
        self.assertEqual(abrigo.porcentaje_descuento, Decimal("10.00"))

    def test_product_without_promotion_keeps_its_price(self):
        items, _ = self.recommend(20)
        polera = next(item for item in items if item.id_producto == 1)
        self.assertFalse(polera.tiene_promocion)
        self.assertIsNone(polera.promocion)
        self.assertIsNone(polera.monto_descuento)
        self.assertEqual(polera.precio_final, polera.precio_base)

    def test_fixed_amount_promotion_never_goes_below_zero(self):
        self.assertEqual(
            self.service._apply_promotion(
                Decimal("10.00"),
                {"tipo_descuento": "MONTO_FIJO", "valor": Decimal("30.00")},
            ),
            Decimal("0.00"),
        )

    def test_item_exposes_image_category_season_and_score(self):
        items, _ = self.recommend(20)
        item = next(item for item in items if item.id_producto == 1)
        self.assertEqual(item.imagen_principal, "https://cdn.test/1.jpg")
        self.assertEqual(item.categoria, "Poleras")
        self.assertEqual(item.temporada, "Invierno 2026")
        self.assertEqual(item.seccion, "UNISEX")
        self.assertIsInstance(item.score, float)
        self.assertGreaterEqual(item.score, 0.0)
        self.assertTrue(item.motivo)

    def test_ranking_is_deterministic_for_stable_pagination(self):
        self._purchase(1, 1, variant_id=1)
        first = [item.id_producto for item in self.recommend()[0]]
        second = [item.id_producto for item in self.recommend()[0]]
        self.assertEqual(first, second)


class QueryBudgetTests(RecommendationFixture):
    def test_request_is_readonly_and_uses_a_bounded_number_of_queries(self):
        self._purchase(1, 1, variant_id=1)
        statements = []
        event.listen(
            self.engine,
            "before_cursor_execute",
            lambda conn, cursor, statement, params, context, many:
                statements.append(statement),
        )
        with patch.object(self.db, "commit", side_effect=AssertionError("write")), \
                patch.object(self.db, "flush", side_effect=AssertionError("write")):
            items, _ = self.recommend()

        self.assertTrue(items)
        # 7 consultas: cliente, senales, popularidad, promociones, pool,
        # variantes del top e imagenes del top.
        self.assertEqual(len(statements), 7, statements)
        self.assertFalse([s for s in statements if s.lstrip()[:6].upper() in
                          ("INSERT", "UPDATE", "DELETE")])

    def test_no_per_product_queries_when_the_catalog_grows(self):
        """El numero de consultas no depende de la cantidad de candidatos."""
        self._purchase(1, 1, variant_id=1)
        statements = []
        event.listen(
            self.engine,
            "before_cursor_execute",
            lambda conn, cursor, statement, params, context, many:
                statements.append(statement),
        )
        self.recommend()
        baseline = len(statements)

        statements.clear()
        for pid in range(100, 140):
            self.db.add(Product(
                id_producto=pid, id_categoria=1, nombre=f"Polera {pid}",
                seccion="UNISEX", id_temporada=1, precio=Decimal("90.00"),
                estado=True, created_at=NOW, updated_at=NOW,
            ))
            self.db.add(ProductVariant(
                id_variante_producto=pid, id_producto=pid, id_talla=2,
                id_color=1, sku=f"SKU-{pid}", estado=True,
                created_at=NOW, updated_at=NOW,
            ))
            self.db.add(BranchInventory(
                id_inventario_sucursal=pid, id_sucursal=1,
                id_variante_producto=pid, stock_actual=5, stock_reservado=0,
                stock_minimo=0, created_at=NOW, updated_at=NOW,
            ))
        self.db.commit()
        statements.clear()

        items, _ = self.recommend(limit=12)
        self.assertEqual(len(items), 12)
        self.assertEqual(len(statements), baseline, statements)

    def test_candidate_pool_is_bounded(self):
        self.assertEqual(self.service._pool_size(12), 192)
        self.assertEqual(self.service._pool_size(50), 200)
        self.assertEqual(self.service._pool_size(1), 60)


class RepositorySqlTests(TestCase):
    """El SQL emitido debe respetar los filtros obligatorios en PostgreSQL."""

    def setUp(self):
        self.db = MagicMock()
        self.db.execute.return_value.mappings.return_value.all.return_value = []
        self.repository = ClientRecommendationsRepository(self.db)

    def _sql(self):
        return str(
            self.db.execute.call_args.args[0].compile(
                dialect=postgresql.dialect()
            )
        )

    def test_candidate_pool_requires_active_product_variant_and_stock(self):
        self.repository.list_candidates(
            category_ids=(1,), season_ids=(2,), promoted_ids=(3,),
            popular_ids=(4,), branch_id=None, city_id=None,
            today=NOW.date(), limit=200,
        )
        sql = self._sql()
        self.assertIn("t_producto.estado IS true", sql)
        self.assertIn("t_variante_producto.estado IS true", sql)
        self.assertIn("t_sucursal.estado IS true", sql)
        self.assertIn(
            "t_inventario_sucursal.stock_actual - "
            "t_inventario_sucursal.stock_reservado >",
            sql,
        )
        self.assertIn("LIMIT", sql)
        self.assertNotIn("greatest", sql)

    def test_branch_scoped_pool_reuses_the_catalog_availability_filter(self):
        self.repository.list_candidates(
            branch_id=7, city_id=None, today=NOW.date(), limit=50
        )
        sql = self._sql()
        self.assertIn("t_inventario_sucursal.id_sucursal =", sql)
        self.assertIn("t_variante_producto.estado IS true", sql)

    def test_signals_only_read_completed_sales_and_valid_reservations(self):
        self.repository.list_affinity_signals(
            1, since=NOW - timedelta(days=365)
        )
        sql = self._sql()
        self.assertIn("UNION ALL", sql)
        self.assertIn("t_venta.estado = ", sql)
        self.assertIn("t_reserva.estado IN ", sql)
        self.assertIn("t_carrito.estado = ", sql)
        self.assertIn("LIMIT", sql)

    def test_popularity_and_promotions_are_bounded(self):
        self.repository.list_recent_popularity(since=NOW - timedelta(days=90))
        popularity = self._sql()
        self.assertIn("GROUP BY t_variante_producto.id_producto", popularity)
        self.assertIn("LIMIT", popularity)

        self.repository.list_current_promotions(now=NOW)
        promotions = self._sql()
        self.assertIn("t_promocion.estado IS true", promotions)
        self.assertIn("t_promocion.fecha_inicio <=", promotions)
        self.assertIn("t_promocion.fecha_fin >=", promotions)

    def test_variant_and_image_batches_use_in_clauses(self):
        self.repository.list_available_variants(
            [1, 2, 3], branch_id=None, city_id=None
        )
        variants = self._sql()
        self.assertIn("t_variante_producto.id_producto IN ", variants)
        self.assertIn("HAVING", variants)

        self.repository.list_principal_images([1, 2, 3])
        self.assertIn("t_imagen_producto.id_producto IN ", self._sql())

    def test_empty_batches_do_not_touch_the_database(self):
        self.assertEqual(
            self.repository.list_available_variants(
                [], branch_id=None, city_id=None
            ),
            [],
        )
        self.assertEqual(self.repository.list_principal_images([]), [])
        self.db.execute.assert_not_called()


class SecurityAndRouteTests(RecommendationFixture):
    def test_route_is_registered_and_requires_authentication(self):
        registered = {
            (method, route.path)
            for route in routes.router.routes
            for method in route.methods
        }
        self.assertEqual(
            registered, {("GET", "/api/client/recommendations")}
        )
        from app.main import app

        operation = app.openapi()["paths"]["/api/client/recommendations"]["get"]
        self.assertTrue(operation.get("security"))
        params = {item["name"]: item for item in operation["parameters"]}
        self.assertEqual(params["limit"]["schema"]["default"], 12)
        self.assertEqual(params["limit"]["schema"]["maximum"], 50)
        self.assertIn("id_sucursal", params)
        self.assertIn("id_ciudad", params)

    def test_authenticated_client_receives_the_envelope(self):
        self._purchase(1, 1, variant_id=1)
        status, body = request(self.app, "?limit=3")
        self.assertEqual(status, 200)
        self.assertTrue(body["success"])
        self.assertEqual(body["origen"], "PERSONALIZADO")
        self.assertLessEqual(len(body["data"]), 3)
        item = body["data"][0]
        # Los importes viajan como cadena, igual que en CU23 y CU25.
        self.assertIsInstance(item["precio_final"], str)
        self.assertIn("variante_sugerida", item)
        self.assertIn("motivo", item)
        self.assertIn("score", item)

    def test_client_without_profile_gets_403(self):
        self.app.dependency_overrides[require_client] = lambda: NS(
            id_usuario=999, rol="CLIENTE"
        )
        status, body = request(self.app)
        self.assertEqual(status, 403)
        self.assertFalse(body["success"])

    def test_non_client_role_is_rejected_by_the_shared_dependency(self):
        app = FastAPI()
        app.include_router(routes.router)
        app.dependency_overrides[get_db] = lambda: self.db
        with patch("app.routers.client_reservations.AuthService") as auth:
            auth.return_value.get_current_user.return_value = NS(
                id_usuario=10, rol="ADMINISTRADOR"
            )
            self.assertEqual(request(app)[0], 403)

    def test_request_without_token_is_unauthorized(self):
        app = FastAPI()
        app.include_router(routes.router)
        app.dependency_overrides[get_db] = lambda: self.db
        self.assertEqual(request(app, token=False)[0], 401)

    def test_invalid_limit_is_rejected_before_querying(self):
        self.assertEqual(request(self.app, "?limit=0")[0], 422)
        self.assertEqual(request(self.app, "?limit=51")[0], 422)
        self.assertEqual(request(self.app, "?id_sucursal=0")[0], 422)

    def test_unknown_branch_returns_404_and_inactive_returns_422(self):
        self.assertEqual(request(self.app, "?id_sucursal=999")[0], 404)
        self.db.get(Branch, 1).estado = False
        self.db.commit()
        self.assertEqual(request(self.app, "?id_sucursal=1")[0], 422)

    def test_internal_errors_do_not_leak_details(self):
        with patch.object(
            routes, "ClientRecommendationsService"
        ) as service:
            service.return_value.recommend.side_effect = RuntimeError(
                "private database data"
            )
            status, body = request(self.app)
        self.assertEqual(status, 500)
        self.assertNotIn("private", json.dumps(body))
