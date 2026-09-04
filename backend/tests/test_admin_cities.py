"""Pruebas unitarias de la gestión administrativa de ciudades."""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock

from pydantic import ValidationError

from app.routers.admin_cities import router
from app.schemas.admin_city import (
    CityCreateRequest,
    CityStatusUpdateRequest,
    CityUpdateRequest,
)
from app.services.admin_city_service import (
    AdminCityService,
    CityNameDuplicateError,
    CityNotFoundError,
)


def _city(
    city_id: int = 7,
    name: str = "Cochabamba",
    state: bool = True,
) -> SimpleNamespace:
    return SimpleNamespace(
        id_ciudad=city_id,
        nombre=name,
        estado=state,
    )


class AdminCitySchemaTests(TestCase):
    """Valida normalización y contratos cerrados de entrada."""

    def test_city_name_is_trimmed(self) -> None:
        payload = CityCreateRequest(nombre="  Santa Cruz de la Sierra  ")

        self.assertEqual(payload.nombre, "Santa Cruz de la Sierra")

    def test_blank_city_name_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            CityCreateRequest(nombre="   ")


class AdminCityServiceTests(TestCase):
    """Comprueba las reglas de negocio y la persistencia lógica."""

    def setUp(self) -> None:
        self.db = MagicMock()
        self.service = AdminCityService(self.db)
        self.service.repository = MagicMock()

    def test_creation_is_active_by_default(self) -> None:
        city = _city(name="Tarija")
        self.service.repository.get_by_name.return_value = None
        self.service.repository.create.return_value = city

        result = self.service.create_city(CityCreateRequest(nombre="Tarija"))

        self.service.repository.create.assert_called_once_with(name="Tarija")
        self.db.commit.assert_called_once_with()
        self.assertTrue(result.estado)

    def test_duplicate_creation_is_rejected_case_insensitively(self) -> None:
        self.service.repository.get_by_name.return_value = _city()

        with self.assertRaises(CityNameDuplicateError):
            self.service.create_city(CityCreateRequest(nombre="cochabamba"))

        self.service.repository.get_by_name.assert_called_once_with("cochabamba")
        self.service.repository.create.assert_not_called()
        self.db.rollback.assert_called_once_with()

    def test_update_excludes_the_current_city_from_duplicate_check(self) -> None:
        city = _city()
        self.service.repository.get_by_id.return_value = city
        self.service.repository.get_by_name.return_value = None

        result = self.service.update_city(
            city_id=7,
            payload=CityUpdateRequest(nombre="Cochabamba"),
        )

        self.service.repository.get_by_name.assert_called_once_with(
            "Cochabamba",
            exclude_city_id=7,
        )
        self.service.repository.update_name.assert_called_once_with(
            city,
            name="Cochabamba",
        )
        self.db.commit.assert_called_once_with()
        self.assertEqual(result.nombre, "Cochabamba")

    def test_missing_city_cannot_be_updated(self) -> None:
        self.service.repository.get_by_id.return_value = None

        with self.assertRaises(CityNotFoundError):
            self.service.update_city(
                city_id=999,
                payload=CityUpdateRequest(nombre="Oruro"),
            )

        self.service.repository.update_name.assert_not_called()
        self.db.rollback.assert_called_once_with()

    def test_status_update_never_deletes_the_city(self) -> None:
        city = _city()
        self.service.repository.get_by_id.return_value = city
        self.service.repository.update_status.side_effect = (
            lambda target, *, state: setattr(target, "estado", state)
        )

        result = self.service.update_status(
            city_id=7,
            payload=CityStatusUpdateRequest(estado=False),
        )

        self.service.repository.update_status.assert_called_once_with(
            city,
            state=False,
        )
        self.db.delete.assert_not_called()
        self.db.commit.assert_called_once_with()
        self.assertFalse(result.estado)


class AdminCityRouteTests(TestCase):
    """Documenta los cinco endpoints requeridos por CU04."""

    def test_required_routes_are_registered(self) -> None:
        registered = {
            (method, route.path)
            for route in router.routes
            for method in route.methods
        }
        expected = {
            ("GET", "/api/admin/cities"),
            ("GET", "/api/admin/cities/{id_ciudad}"),
            ("POST", "/api/admin/cities"),
            ("PATCH", "/api/admin/cities/{id_ciudad}"),
            ("PATCH", "/api/admin/cities/{id_ciudad}/status"),
        }

        self.assertTrue(expected.issubset(registered))
