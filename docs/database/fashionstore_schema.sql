-- =====================================================
-- FASHIONSTORE
-- Script de base de datos
-- PostgreSQL
-- Ciclo 1
-- =====================================================

-- =====================================================
-- 1. TABLA DE ROLES
-- =====================================================

CREATE TABLE t_rol (
    id_rol SERIAL PRIMARY KEY,
    nombre VARCHAR(50) NOT NULL UNIQUE,
    descripcion VARCHAR(150),
    estado BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- =====================================================
-- 2. TABLA DE CIUDADES
-- =====================================================

CREATE TABLE t_ciudad (
    id_ciudad SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL UNIQUE,
    estado BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- =====================================================
-- 3. TABLA DE CATEGORIAS
-- =====================================================

CREATE TABLE t_categoria (
    id_categoria SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL UNIQUE,
    descripcion VARCHAR(200),
    estado BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- 4. TABLA DE TALLAS
-- =====================================================

CREATE TABLE t_talla (
    id_talla SERIAL PRIMARY KEY,
    nombre VARCHAR(20) NOT NULL UNIQUE,
    descripcion VARCHAR(100),
    estado BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- 5. TABLA DE COLORES
-- =====================================================

CREATE TABLE t_color (
    id_color SERIAL PRIMARY KEY,
    nombre VARCHAR(50) NOT NULL UNIQUE,
    codigo_hex VARCHAR(7),
    estado BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- 6. TABLA DE TEMPORADAS
-- =====================================================

CREATE TABLE t_temporada (
    id_temporada SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    descripcion VARCHAR(200),
    fecha_inicio DATE,
    fecha_fin DATE,
    estado BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- 7. TABLA DE PROVEEDORES
-- =====================================================

CREATE TABLE t_proveedor (
    id_proveedor SERIAL PRIMARY KEY,
    id_usuario INTEGER UNIQUE,
    nombre VARCHAR(150) NOT NULL,
    nit VARCHAR(30),
    telefono VARCHAR(30),
    correo VARCHAR(150),
    direccion VARCHAR(200),
    estado BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_proveedor_usuario
        FOREIGN KEY (id_usuario)
        REFERENCES t_usuario(id_usuario)
        ON DELETE SET NULL
);

-- =====================================================
-- 8. TABLA DE USUARIOS
-- =====================================================

CREATE TABLE t_usuario (
    id_usuario SERIAL PRIMARY KEY,
    id_rol INTEGER NOT NULL,

    nombre VARCHAR(100) NOT NULL,
    apellido VARCHAR(100) NOT NULL,
    correo VARCHAR(150) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,

    telefono VARCHAR(30),
    estado BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_usuario_rol
        FOREIGN KEY (id_rol)
        REFERENCES t_rol(id_rol)
);

-- =====================================================
-- 9. TABLA DE CLIENTES
-- =====================================================

CREATE TABLE t_cliente (
    id_cliente SERIAL PRIMARY KEY,
    id_usuario INTEGER NOT NULL UNIQUE,

    fecha_nacimiento DATE,
    genero VARCHAR(30),

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_cliente_usuario
        FOREIGN KEY (id_usuario)
        REFERENCES t_usuario(id_usuario)
);

-- =====================================================
-- 10. TABLA DE EMPLEADOS
-- =====================================================

CREATE TABLE t_empleado (
    id_empleado SERIAL PRIMARY KEY,
    id_usuario INTEGER NOT NULL UNIQUE,

    ci VARCHAR(30),
    cargo VARCHAR(100),

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_empleado_usuario
        FOREIGN KEY (id_usuario)
        REFERENCES t_usuario(id_usuario)
);

-- =====================================================
-- 11. TABLA DE SUCURSALES
-- =====================================================

CREATE TABLE t_sucursal (
    id_sucursal SERIAL PRIMARY KEY,
    id_ciudad INTEGER NOT NULL,

    nombre VARCHAR(150) NOT NULL,
    direccion VARCHAR(200) NOT NULL,
    telefono VARCHAR(30),

    hora_apertura TIME,
    hora_cierre TIME,

    estado BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_sucursal_ciudad
        FOREIGN KEY (id_ciudad)
        REFERENCES t_ciudad(id_ciudad)
);

-- =====================================================
-- 12. EMPLEADOS POR SUCURSAL
-- =====================================================

CREATE TABLE t_empleado_sucursal (
    id_empleado_sucursal SERIAL PRIMARY KEY,
    id_empleado INTEGER NOT NULL,
    id_sucursal INTEGER NOT NULL,

    fecha_asignacion DATE NOT NULL DEFAULT CURRENT_DATE,
    estado BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT fk_empleado_sucursal_empleado
        FOREIGN KEY (id_empleado)
        REFERENCES t_empleado(id_empleado),

    CONSTRAINT fk_empleado_sucursal_sucursal
        FOREIGN KEY (id_sucursal)
        REFERENCES t_sucursal(id_sucursal),

    CONSTRAINT uq_empleado_sucursal
        UNIQUE (id_empleado, id_sucursal)
);

-- =====================================================
-- 13. TABLA DE PRODUCTOS
-- =====================================================

CREATE TABLE t_producto (
    id_producto SERIAL PRIMARY KEY,

    id_categoria INTEGER NOT NULL,
    id_temporada INTEGER,

    nombre VARCHAR(150) NOT NULL,
    seccion VARCHAR(20) NOT NULL,
    descripcion TEXT,

    precio NUMERIC(10,2) NOT NULL CHECK (precio >= 0),

    estado BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT ck_producto_seccion
        CHECK (seccion IN ('HOMBRE', 'MUJER', 'UNISEX')),

    CONSTRAINT fk_producto_categoria
        FOREIGN KEY (id_categoria)
        REFERENCES t_categoria(id_categoria),

    CONSTRAINT fk_producto_temporada
        FOREIGN KEY (id_temporada)
        REFERENCES t_temporada(id_temporada)
);

-- =====================================================
-- 14. VARIANTES DE PRODUCTO
-- =====================================================

CREATE TABLE t_variante_producto (
    id_variante_producto SERIAL PRIMARY KEY,

    id_producto INTEGER NOT NULL,
    id_talla INTEGER NOT NULL,
    id_color INTEGER NOT NULL,

    sku VARCHAR(100) NOT NULL UNIQUE,
    estado BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_variante_producto
        FOREIGN KEY (id_producto)
        REFERENCES t_producto(id_producto),

    CONSTRAINT fk_variante_talla
        FOREIGN KEY (id_talla)
        REFERENCES t_talla(id_talla),

    CONSTRAINT fk_variante_color
        FOREIGN KEY (id_color)
        REFERENCES t_color(id_color),

    CONSTRAINT uq_producto_talla_color
        UNIQUE (id_producto, id_talla, id_color)
);

-- =====================================================
-- 15. PRODUCTOS POR PROVEEDOR
-- =====================================================

CREATE TABLE t_producto_proveedor (
    id_producto_proveedor SERIAL PRIMARY KEY,

    id_producto INTEGER NOT NULL,
    id_proveedor INTEGER NOT NULL,

    costo_referencia NUMERIC(10,2)
        CHECK (costo_referencia >= 0),

    estado BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT fk_producto_proveedor_producto
        FOREIGN KEY (id_producto)
        REFERENCES t_producto(id_producto),

    CONSTRAINT fk_producto_proveedor_proveedor
        FOREIGN KEY (id_proveedor)
        REFERENCES t_proveedor(id_proveedor),

    CONSTRAINT uq_producto_proveedor
        UNIQUE (id_producto, id_proveedor)
);

-- =====================================================
-- 16. IMAGENES DE PRODUCTOS
-- =====================================================

CREATE TABLE t_imagen_producto (
    id_imagen_producto SERIAL PRIMARY KEY,
    id_producto INTEGER NOT NULL,

    url_imagen TEXT NOT NULL,
    es_principal BOOLEAN NOT NULL DEFAULT FALSE,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_imagen_producto
        FOREIGN KEY (id_producto)
        REFERENCES t_producto(id_producto)
        ON DELETE CASCADE
);

-- =====================================================
-- 17. TABLA DE COLECCIONES
-- =====================================================

CREATE TABLE t_coleccion (
    id_coleccion SERIAL PRIMARY KEY,

    nombre VARCHAR(100) NOT NULL,
    descripcion VARCHAR(200),

    estado BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- 18. PRODUCTOS POR COLECCION
-- =====================================================

CREATE TABLE t_producto_coleccion (
    id_producto_coleccion SERIAL PRIMARY KEY,

    id_producto INTEGER NOT NULL,
    id_coleccion INTEGER NOT NULL,

    CONSTRAINT fk_producto_coleccion_producto
        FOREIGN KEY (id_producto)
        REFERENCES t_producto(id_producto),

    CONSTRAINT fk_producto_coleccion_coleccion
        FOREIGN KEY (id_coleccion)
        REFERENCES t_coleccion(id_coleccion),

    CONSTRAINT uq_producto_coleccion
        UNIQUE (id_producto, id_coleccion)
);

