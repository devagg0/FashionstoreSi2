"""Inserta los datos base de FashionStore de forma idempotente."""

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.category import Category
from app.models.city import City
from app.models.color import Color
from app.models.role import Role
from app.models.size import Size


ROLES = (
    (
        "ADMINISTRADOR",
        "Gestiona la configuración general de FashionStore",
    ),
    ("CLIENTE", "Usuario que consulta, reserva y compra prendas"),
    ("ENCARGADO_SUCURSAL", "Gestiona operaciones de una sucursal"),
    ("CAJERO", "Registra ventas y pagos presenciales"),
    (
        "PROVEEDOR",
        "Proveedor autorizado para interactuar con FashionStore",
    ),
)

CIUDADES = (
    "Santa Cruz de la Sierra",
    "Cochabamba",
    "La Paz",
    "Sucre",
)

CATEGORIAS = (
    ("Poleras", "Prendas superiores de uso casual"),
    ("Camisas", "Camisas para diferentes estilos y ocasiones"),
    ("Pantalones", "Pantalones de distintos cortes y materiales"),
    ("Shorts", "Prendas cortas para la parte inferior"),
    ("Chaquetas", "Prendas exteriores y de abrigo"),
    ("Vestidos", "Vestidos para diferentes estilos y ocasiones"),
)

TALLAS = (
    ("XS", "Talla extra pequeña"),
    ("S", "Talla pequeña"),
    ("M", "Talla mediana"),
    ("L", "Talla grande"),
    ("XL", "Talla extra grande"),
    ("XXL", "Talla doble extra grande"),
)

COLORES = (
    ("Negro", "#000000"),
    ("Blanco", "#FFFFFF"),
    ("Gris", "#808080"),
    ("Azul", "#0000FF"),
    ("Rojo", "#FF0000"),
    ("Verde", "#008000"),
    ("Beige", "#F5F5DC"),
    ("Marrón", "#8B4513"),
)


def seed_base() -> None:
    """Crea solamente los registros base que todavía no existen."""
    session = SessionLocal()

    try:
        for nombre, descripcion in ROLES:
            existing = session.scalar(select(Role).where(Role.nombre == nombre))
            if existing is not None:
                print(f"Rol existente, se omite: {nombre}")
                continue

            session.add(
                Role(nombre=nombre, descripcion=descripcion, estado=True)
            )
            print(f"Rol preparado para crear: {nombre}")

        for nombre in CIUDADES:
            existing = session.scalar(select(City).where(City.nombre == nombre))
            if existing is not None:
                print(f"Ciudad existente, se omite: {nombre}")
                continue

            session.add(City(nombre=nombre, estado=True))
            print(f"Ciudad preparada para crear: {nombre}")

        for nombre, descripcion in CATEGORIAS:
            existing = session.scalar(
                select(Category).where(Category.nombre == nombre)
            )
            if existing is not None:
                print(f"Categoría existente, se omite: {nombre}")
                continue

            session.add(
                Category(nombre=nombre, descripcion=descripcion, estado=True)
            )
            print(f"Categoría preparada para crear: {nombre}")

        for nombre, descripcion in TALLAS:
            existing = session.scalar(select(Size).where(Size.nombre == nombre))
            if existing is not None:
                print(f"Talla existente, se omite: {nombre}")
                continue

            session.add(Size(nombre=nombre, descripcion=descripcion, estado=True))
            print(f"Talla preparada para crear: {nombre}")

        for nombre, codigo_hex in COLORES:
            existing = session.scalar(select(Color).where(Color.nombre == nombre))
            if existing is not None:
                print(f"Color existente, se omite: {nombre}")
                continue

            session.add(
                Color(nombre=nombre, codigo_hex=codigo_hex, estado=True)
            )
            print(f"Color preparado para crear: {nombre}")

        session.commit()
        print("Datos base procesados correctamente.")
    except Exception:
        session.rollback()
        print("Error al insertar los datos base. Se revirtió toda la transacción.")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    seed_base()
