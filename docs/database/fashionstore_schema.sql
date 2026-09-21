-- =====================================================
-- FASHIONSTORE
-- Script de base de datos
-- PostgreSQL
-- Esquema documental consolidado: ciclos 1, 2 y 3
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

-- =====================================================
-- USUARIOS Y ACCESO (TABLAS INCORPORADAS)
-- =====================================================

CREATE TABLE t_recuperacion_contrasena (
    id_recuperacion SERIAL,
    id_usuario INTEGER NOT NULL,
    codigo_hash VARCHAR(64) NOT NULL,
    intentos INTEGER NOT NULL DEFAULT 0,
    usado BOOLEAN NOT NULL DEFAULT FALSE,
    expira_en TIMESTAMP WITH TIME ZONE NOT NULL,
    creado_en TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_recuperacion_contrasena PRIMARY KEY (id_recuperacion),
    CONSTRAINT fk_recuperacion_contrasena_usuario FOREIGN KEY (id_usuario)
        REFERENCES t_usuario(id_usuario) ON DELETE CASCADE
);

CREATE INDEX ix_t_recuperacion_contrasena_id_usuario
    ON t_recuperacion_contrasena (id_usuario);

-- =====================================================
-- CATALOGO Y ABASTECIMIENTO (TABLAS INCORPORADAS)
-- =====================================================

CREATE TABLE t_promocion (
    id_promocion SERIAL PRIMARY KEY,
    nombre VARCHAR(150) NOT NULL,
    codigo VARCHAR(50) UNIQUE,
    descripcion VARCHAR(200),
    tipo_descuento VARCHAR(20) NOT NULL,
    valor NUMERIC(10,2) NOT NULL,
    fecha_inicio TIMESTAMP NOT NULL,
    fecha_fin TIMESTAMP NOT NULL,
    acumulable BOOLEAN NOT NULL DEFAULT FALSE,
    estado BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_promocion_tipo_descuento CHECK (tipo_descuento IN ('PORCENTAJE', 'MONTO_FIJO')),
    CONSTRAINT ck_promocion_valor_positivo CHECK (valor > 0),
    CONSTRAINT ck_promocion_porcentaje_valido CHECK (tipo_descuento <> 'PORCENTAJE' OR valor <= 100),
    CONSTRAINT ck_promocion_rango_fechas CHECK (fecha_fin >= fecha_inicio)
);
CREATE INDEX ix_promocion_vigencia ON t_promocion (estado, fecha_inicio, fecha_fin);

CREATE TABLE t_promocion_producto (
    id_promocion_producto SERIAL PRIMARY KEY,
    id_promocion INTEGER NOT NULL REFERENCES t_promocion(id_promocion) ON DELETE CASCADE,
    id_producto INTEGER NOT NULL REFERENCES t_producto(id_producto) ON DELETE CASCADE,
    CONSTRAINT uq_promocion_producto UNIQUE (id_promocion, id_producto)
);
CREATE INDEX ix_promocion_producto_id_producto ON t_promocion_producto (id_producto);

-- =====================================================
-- INVENTARIO
-- =====================================================

CREATE TABLE t_inventario_sucursal (
    id_inventario_sucursal SERIAL PRIMARY KEY,
    id_sucursal INTEGER NOT NULL REFERENCES t_sucursal(id_sucursal),
    id_variante_producto INTEGER NOT NULL REFERENCES t_variante_producto(id_variante_producto),
    stock_actual INTEGER NOT NULL DEFAULT 0,
    stock_reservado INTEGER NOT NULL DEFAULT 0,
    stock_minimo INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_inventario_stock_actual CHECK (stock_actual >= 0),
    CONSTRAINT ck_inventario_stock_reservado CHECK (stock_reservado >= 0),
    CONSTRAINT ck_inventario_stock_minimo CHECK (stock_minimo >= 0),
    CONSTRAINT ck_inventario_reservado_disponible CHECK (stock_reservado <= stock_actual),
    CONSTRAINT uq_inventario_sucursal_variante UNIQUE (id_sucursal, id_variante_producto)
);
CREATE INDEX ix_inventario_sucursal_id_variante_producto ON t_inventario_sucursal (id_variante_producto);

-- La FK de id_venta se agrega después de crear t_venta para evitar la dependencia circular.
CREATE TABLE t_movimiento_inventario (
    id_movimiento_inventario SERIAL PRIMARY KEY,
    id_sucursal_origen INTEGER REFERENCES t_sucursal(id_sucursal),
    id_sucursal_destino INTEGER REFERENCES t_sucursal(id_sucursal),
    id_empleado_sucursal INTEGER REFERENCES t_empleado_sucursal(id_empleado_sucursal),
    id_venta INTEGER,
    tipo_movimiento VARCHAR(30) NOT NULL,
    estado VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE',
    motivo VARCHAR(200),
    fecha_movimiento TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_movimiento_inventario_venta UNIQUE (id_venta),
    CONSTRAINT ck_movimiento_inventario_tipo CHECK (tipo_movimiento IN ('ENTRADA','SALIDA','TRANSFERENCIA','AJUSTE_POSITIVO','AJUSTE_NEGATIVO','VENTA')),
    CONSTRAINT ck_movimiento_inventario_estado CHECK (estado IN ('PENDIENTE','CONFIRMADO','ANULADO')),
    CONSTRAINT ck_movimiento_inventario_sucursales CHECK (
        (tipo_movimiento = 'TRANSFERENCIA' AND id_sucursal_origen IS NOT NULL AND id_sucursal_destino IS NOT NULL AND id_sucursal_origen <> id_sucursal_destino)
        OR (tipo_movimiento IN ('ENTRADA','AJUSTE_POSITIVO') AND id_sucursal_origen IS NULL AND id_sucursal_destino IS NOT NULL)
        OR (tipo_movimiento IN ('SALIDA','AJUSTE_NEGATIVO','VENTA') AND id_sucursal_origen IS NOT NULL AND id_sucursal_destino IS NULL)
    ),
    CONSTRAINT ck_movimiento_inventario_venta CHECK ((tipo_movimiento = 'VENTA' AND id_venta IS NOT NULL) OR (tipo_movimiento <> 'VENTA' AND id_venta IS NULL)),
    CONSTRAINT ck_movimiento_responsable_automatico CHECK (id_empleado_sucursal IS NOT NULL OR (tipo_movimiento = 'VENTA' AND id_venta IS NOT NULL))
);
CREATE INDEX ix_movimiento_inventario_origen_fecha ON t_movimiento_inventario (id_sucursal_origen, fecha_movimiento);
CREATE INDEX ix_movimiento_inventario_destino_fecha ON t_movimiento_inventario (id_sucursal_destino, fecha_movimiento);

CREATE TABLE t_detalle_movimiento_inventario (
    id_detalle_movimiento_inventario SERIAL PRIMARY KEY,
    id_movimiento_inventario INTEGER NOT NULL REFERENCES t_movimiento_inventario(id_movimiento_inventario) ON DELETE CASCADE,
    id_variante_producto INTEGER NOT NULL REFERENCES t_variante_producto(id_variante_producto),
    cantidad INTEGER NOT NULL,
    costo_unitario NUMERIC(10,2),
    CONSTRAINT uq_detalle_movimiento_variante UNIQUE (id_movimiento_inventario, id_variante_producto),
    CONSTRAINT ck_detalle_movimiento_cantidad CHECK (cantidad > 0),
    CONSTRAINT ck_detalle_movimiento_costo CHECK (costo_unitario IS NULL OR costo_unitario >= 0)
);
CREATE INDEX ix_detalle_movimiento_id_variante_producto ON t_detalle_movimiento_inventario (id_variante_producto);

-- =====================================================
-- RESERVAS
-- =====================================================

CREATE TABLE t_reserva (
    id_reserva SERIAL PRIMARY KEY,
    id_cliente INTEGER NOT NULL REFERENCES t_cliente(id_cliente),
    id_sucursal INTEGER NOT NULL REFERENCES t_sucursal(id_sucursal),
    id_empleado_atencion INTEGER,
    codigo VARCHAR(50) NOT NULL UNIQUE,
    estado VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE',
    fecha_expiracion TIMESTAMP NOT NULL,
    fecha_atencion_programada TIMESTAMP NOT NULL,
    fecha_atencion TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_reserva_empleado_sucursal FOREIGN KEY (id_empleado_atencion, id_sucursal) REFERENCES t_empleado_sucursal(id_empleado, id_sucursal),
    CONSTRAINT ck_reserva_estado CHECK (estado IN ('PENDIENTE','CONFIRMADA','ATENDIDA','CANCELADA','EXPIRADA')),
    CONSTRAINT ck_reserva_fecha_expiracion CHECK (fecha_expiracion > created_at),
    CONSTRAINT ck_reserva_expiracion_programada CHECK (fecha_expiracion > fecha_atencion_programada)
);
COMMENT ON COLUMN t_reserva.fecha_atencion_programada IS 'Fecha y hora elegida por el cliente para acudir a la sucursal';
CREATE INDEX ix_reserva_cliente_created_at ON t_reserva (id_cliente, created_at);
CREATE INDEX ix_reserva_sucursal_estado ON t_reserva (id_sucursal, estado);

CREATE TABLE t_detalle_reserva (
    id_detalle_reserva SERIAL PRIMARY KEY,
    id_reserva INTEGER NOT NULL REFERENCES t_reserva(id_reserva) ON DELETE CASCADE,
    id_variante_producto INTEGER NOT NULL REFERENCES t_variante_producto(id_variante_producto),
    cantidad INTEGER NOT NULL,
    precio_unitario NUMERIC(10,2) NOT NULL,
    CONSTRAINT uq_detalle_reserva_variante UNIQUE (id_reserva, id_variante_producto),
    CONSTRAINT ck_detalle_reserva_cantidad CHECK (cantidad > 0),
    CONSTRAINT ck_detalle_reserva_precio CHECK (precio_unitario >= 0)
);
CREATE INDEX ix_detalle_reserva_id_variante_producto ON t_detalle_reserva (id_variante_producto);

CREATE TABLE t_carrito (
    id_carrito SERIAL PRIMARY KEY,
    id_cliente INTEGER NOT NULL REFERENCES t_cliente(id_cliente),
    estado VARCHAR(20) NOT NULL DEFAULT 'ACTIVO',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_carrito_estado CHECK (estado IN ('ACTIVO','CONVERTIDO','ABANDONADO'))
);
CREATE UNIQUE INDEX uq_carrito_cliente_activo ON t_carrito (id_cliente) WHERE estado = 'ACTIVO';

CREATE TABLE t_detalle_carrito (
    id_detalle_carrito SERIAL PRIMARY KEY,
    id_carrito INTEGER NOT NULL REFERENCES t_carrito(id_carrito) ON DELETE CASCADE,
    id_variante_producto INTEGER NOT NULL REFERENCES t_variante_producto(id_variante_producto),
    cantidad INTEGER NOT NULL,
    CONSTRAINT uq_detalle_carrito_variante UNIQUE (id_carrito, id_variante_producto),
    CONSTRAINT ck_detalle_carrito_cantidad CHECK (cantidad > 0)
);

-- =====================================================
-- VENTAS Y PAGOS
-- =====================================================

CREATE TABLE t_venta (
    id_venta SERIAL PRIMARY KEY,
    id_sucursal INTEGER NOT NULL REFERENCES t_sucursal(id_sucursal),
    id_empleado INTEGER,
    id_cliente INTEGER REFERENCES t_cliente(id_cliente),
    id_reserva INTEGER,
    canal VARCHAR(20) NOT NULL DEFAULT 'PRESENCIAL',
    moneda VARCHAR(3) NOT NULL DEFAULT 'BOB',
    id_carrito INTEGER,
    fecha_completada TIMESTAMP,
    fecha_expiracion_pago TIMESTAMP,
    stock_comprometido BOOLEAN NOT NULL DEFAULT FALSE,
    numero_venta VARCHAR(50) NOT NULL UNIQUE,
    estado VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE',
    subtotal NUMERIC(12,2) NOT NULL,
    descuento_total NUMERIC(12,2) NOT NULL DEFAULT 0,
    total NUMERIC(12,2) NOT NULL,
    fecha_venta TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_venta_empleado_sucursal FOREIGN KEY (id_empleado, id_sucursal) REFERENCES t_empleado_sucursal(id_empleado, id_sucursal),
    CONSTRAINT fk_venta_reserva FOREIGN KEY (id_reserva) REFERENCES t_reserva(id_reserva),
    CONSTRAINT fk_venta_carrito FOREIGN KEY (id_carrito) REFERENCES t_carrito(id_carrito) ON DELETE RESTRICT,
    CONSTRAINT uq_venta_reserva UNIQUE (id_reserva),
    CONSTRAINT uq_venta_carrito UNIQUE (id_carrito),
    CONSTRAINT ck_venta_canal CHECK (canal IN ('PRESENCIAL','DIGITAL')),
    CONSTRAINT ck_venta_moneda CHECK (moneda = 'BOB'),
    CONSTRAINT ck_venta_empleado_canal CHECK (canal = 'DIGITAL' OR id_empleado IS NOT NULL),
    CONSTRAINT ck_venta_cliente_digital CHECK (canal <> 'DIGITAL' OR id_cliente IS NOT NULL),
    CONSTRAINT ck_venta_carrito_canal CHECK (id_carrito IS NULL OR canal = 'DIGITAL'),
    CONSTRAINT ck_venta_fecha_completada CHECK ((estado <> 'PENDIENTE' OR fecha_completada IS NULL) AND (estado <> 'COMPLETADA' OR fecha_completada IS NOT NULL) AND (fecha_completada IS NULL OR fecha_completada >= fecha_venta)),
    CONSTRAINT ck_venta_expiracion_pago CHECK (fecha_expiracion_pago IS NULL OR fecha_expiracion_pago > created_at),
    CONSTRAINT ck_venta_stock_comprometido CHECK (NOT stock_comprometido OR (canal = 'DIGITAL' AND estado = 'PENDIENTE')),
    CONSTRAINT ck_venta_estado CHECK (estado IN ('PENDIENTE','COMPLETADA','ANULADA')),
    CONSTRAINT ck_venta_subtotal CHECK (subtotal >= 0),
    CONSTRAINT ck_venta_descuento_total CHECK (descuento_total >= 0 AND descuento_total <= subtotal),
    CONSTRAINT ck_venta_total CHECK (total >= 0),
    CONSTRAINT ck_venta_calculo_total CHECK (total = subtotal - descuento_total)
);
ALTER TABLE t_movimiento_inventario ADD CONSTRAINT fk_movimiento_inventario_venta FOREIGN KEY (id_venta) REFERENCES t_venta(id_venta);
CREATE INDEX ix_venta_sucursal_fecha ON t_venta (id_sucursal, fecha_venta);
CREATE INDEX ix_venta_cliente_fecha ON t_venta (id_cliente, fecha_venta);
CREATE INDEX ix_venta_expiracion_comprometida ON t_venta (fecha_expiracion_pago) WHERE estado = 'PENDIENTE' AND stock_comprometido;
CREATE INDEX ix_venta_fecha_completada ON t_venta (fecha_completada) WHERE fecha_completada IS NOT NULL;

CREATE TABLE t_detalle_venta (
    id_detalle_venta SERIAL PRIMARY KEY,
    id_venta INTEGER NOT NULL REFERENCES t_venta(id_venta) ON DELETE CASCADE,
    id_variante_producto INTEGER NOT NULL REFERENCES t_variante_producto(id_variante_producto),
    id_promocion INTEGER REFERENCES t_promocion(id_promocion),
    cantidad INTEGER NOT NULL,
    precio_unitario NUMERIC(10,2) NOT NULL,
    descuento_unitario NUMERIC(10,2) NOT NULL DEFAULT 0,
    subtotal_linea NUMERIC(12,2) NOT NULL,
    CONSTRAINT uq_detalle_venta_variante UNIQUE (id_venta, id_variante_producto),
    CONSTRAINT ck_detalle_venta_cantidad CHECK (cantidad > 0),
    CONSTRAINT ck_detalle_venta_precio CHECK (precio_unitario >= 0),
    CONSTRAINT ck_detalle_venta_descuento CHECK (descuento_unitario >= 0 AND descuento_unitario <= precio_unitario),
    CONSTRAINT ck_detalle_venta_subtotal CHECK (subtotal_linea >= 0),
    CONSTRAINT ck_detalle_venta_calculo_subtotal CHECK (subtotal_linea = cantidad * (precio_unitario - descuento_unitario))
);
CREATE INDEX ix_detalle_venta_id_variante_producto ON t_detalle_venta (id_variante_producto);

CREATE TABLE t_pago (
    id_pago SERIAL PRIMARY KEY,
    id_venta INTEGER NOT NULL,
    medio VARCHAR(20) NOT NULL,
    proveedor VARCHAR(20) NOT NULL,
    entorno VARCHAR(20) NOT NULL,
    estado VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE',
    monto NUMERIC(12,2) NOT NULL,
    moneda VARCHAR(3) NOT NULL,
    referencia_externa VARCHAR(255),
    clave_idempotencia UUID NOT NULL,
    fecha_aprobacion TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_pago_venta FOREIGN KEY (id_venta) REFERENCES t_venta(id_venta) ON DELETE RESTRICT,
    CONSTRAINT uq_pago_idempotencia UNIQUE (clave_idempotencia),
    CONSTRAINT uq_pago_referencia UNIQUE (proveedor, entorno, referencia_externa),
    CONSTRAINT uq_pago_venta_pertenencia UNIQUE (id_pago, id_venta),
    CONSTRAINT ck_pago_estado CHECK (estado IN ('PENDIENTE','APROBADO','RECHAZADO','CANCELADO','EXPIRADO','REEMBOLSADO')),
    CONSTRAINT ck_pago_medio CHECK (medio IN ('EFECTIVO','QR','TARJETA')),
    CONSTRAINT ck_pago_proveedor CHECK (proveedor IN ('MANUAL','STRIPE')),
    CONSTRAINT ck_pago_entorno CHECK (entorno IN ('LOCAL','TEST')),
    CONSTRAINT ck_pago_combinacion CHECK ((proveedor = 'MANUAL' AND entorno = 'LOCAL' AND medio IN ('EFECTIVO','QR')) OR (proveedor = 'STRIPE' AND entorno = 'TEST' AND medio = 'TARJETA')),
    CONSTRAINT ck_pago_monto CHECK (monto > 0), CONSTRAINT ck_pago_moneda CHECK (moneda = 'BOB'),
    CONSTRAINT ck_pago_referencia CHECK (referencia_externa IS NULL OR length(trim(referencia_externa)) > 0),
    CONSTRAINT ck_pago_aprobacion CHECK (estado NOT IN ('APROBADO','REEMBOLSADO') OR fecha_aprobacion IS NOT NULL),
    CONSTRAINT ck_pago_stripe_referencia CHECK (proveedor <> 'STRIPE' OR estado NOT IN ('APROBADO','REEMBOLSADO') OR referencia_externa IS NOT NULL)
);
CREATE INDEX ix_pago_venta_created_at ON t_pago (id_venta, created_at);
CREATE UNIQUE INDEX uq_pago_venta_cobrado ON t_pago (id_venta) WHERE estado IN ('APROBADO','REEMBOLSADO');
CREATE UNIQUE INDEX uq_pago_venta_pendiente ON t_pago (id_venta) WHERE estado = 'PENDIENTE';

CREATE TABLE t_devolucion (
    id_devolucion SERIAL PRIMARY KEY, id_venta INTEGER NOT NULL, tipo VARCHAR(20) NOT NULL,
    estado VARCHAR(20) NOT NULL DEFAULT 'SOLICITADA', motivo VARCHAR(500) NOT NULL,
    id_usuario_solicitante INTEGER NOT NULL, id_usuario_resolutor INTEGER,
    id_movimiento_inventario INTEGER, clave_idempotencia UUID NOT NULL,
    fecha_resolucion TIMESTAMP, fecha_procesamiento TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_devolucion_venta FOREIGN KEY (id_venta) REFERENCES t_venta(id_venta) ON DELETE RESTRICT,
    CONSTRAINT fk_devolucion_solicitante FOREIGN KEY (id_usuario_solicitante) REFERENCES t_usuario(id_usuario) ON DELETE RESTRICT,
    CONSTRAINT fk_devolucion_resolutor FOREIGN KEY (id_usuario_resolutor) REFERENCES t_usuario(id_usuario) ON DELETE RESTRICT,
    CONSTRAINT fk_devolucion_movimiento FOREIGN KEY (id_movimiento_inventario) REFERENCES t_movimiento_inventario(id_movimiento_inventario) ON DELETE RESTRICT,
    CONSTRAINT uq_devolucion_venta_pertenencia UNIQUE (id_devolucion, id_venta),
    CONSTRAINT uq_devolucion_movimiento UNIQUE (id_movimiento_inventario), CONSTRAINT uq_devolucion_idempotencia UNIQUE (clave_idempotencia),
    CONSTRAINT ck_devolucion_tipo CHECK (tipo IN ('DEVOLUCION','CANCELACION')),
    CONSTRAINT ck_devolucion_estado CHECK (estado IN ('SOLICITADA','APROBADA','RECHAZADA','PROCESADA')),
    CONSTRAINT ck_devolucion_motivo CHECK (length(trim(motivo)) > 0),
    CONSTRAINT ck_devolucion_cancelacion CHECK (tipo <> 'CANCELACION' OR id_movimiento_inventario IS NULL),
    CONSTRAINT ck_devolucion_resolucion CHECK (estado = 'SOLICITADA' OR (id_usuario_resolutor IS NOT NULL AND fecha_resolucion IS NOT NULL)),
    CONSTRAINT ck_devolucion_procesamiento CHECK (estado <> 'PROCESADA' OR fecha_procesamiento IS NOT NULL),
    CONSTRAINT ck_devolucion_fecha_resolucion CHECK (fecha_resolucion IS NULL OR fecha_resolucion >= created_at),
    CONSTRAINT ck_devolucion_fecha_procesamiento CHECK (fecha_procesamiento IS NULL OR (fecha_resolucion IS NOT NULL AND fecha_procesamiento >= fecha_resolucion))
);
CREATE INDEX ix_devolucion_venta_created_at ON t_devolucion (id_venta, created_at);
CREATE INDEX ix_devolucion_estado_created_at ON t_devolucion (estado, created_at);
CREATE UNIQUE INDEX uq_devolucion_cancelacion_activa ON t_devolucion (id_venta) WHERE tipo = 'CANCELACION' AND estado IN ('SOLICITADA','APROBADA','PROCESADA');

CREATE TABLE t_detalle_devolucion (
    id_detalle_devolucion SERIAL PRIMARY KEY, id_devolucion INTEGER NOT NULL, id_venta INTEGER NOT NULL,
    id_variante_producto INTEGER NOT NULL, cantidad INTEGER NOT NULL, cantidad_reintegrar INTEGER NOT NULL DEFAULT 0,
    importe_restitucion NUMERIC(12,2) NOT NULL, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_detalle_devolucion_cabecera FOREIGN KEY (id_devolucion,id_venta) REFERENCES t_devolucion(id_devolucion,id_venta) ON DELETE RESTRICT,
    CONSTRAINT fk_detalle_devolucion_linea_venta FOREIGN KEY (id_venta,id_variante_producto) REFERENCES t_detalle_venta(id_venta,id_variante_producto) ON DELETE RESTRICT,
    CONSTRAINT uq_detalle_devolucion_variante UNIQUE (id_devolucion,id_variante_producto),
    CONSTRAINT ck_detalle_devolucion_cantidad CHECK (cantidad > 0),
    CONSTRAINT ck_detalle_devolucion_reintegro CHECK (cantidad_reintegrar >= 0 AND cantidad_reintegrar <= cantidad),
    CONSTRAINT ck_detalle_devolucion_importe CHECK (importe_restitucion >= 0)
);
CREATE INDEX ix_detalle_devolucion_linea_venta ON t_detalle_devolucion (id_venta,id_variante_producto);

CREATE TABLE t_reembolso (
    id_reembolso SERIAL PRIMARY KEY, id_venta INTEGER NOT NULL, id_pago INTEGER NOT NULL, id_devolucion INTEGER NOT NULL,
    estado VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE', monto NUMERIC(12,2) NOT NULL, referencia_externa VARCHAR(255),
    clave_idempotencia UUID NOT NULL, id_usuario_responsable INTEGER, fecha_aprobacion TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_reembolso_pago_venta FOREIGN KEY (id_pago,id_venta) REFERENCES t_pago(id_pago,id_venta) ON DELETE RESTRICT,
    CONSTRAINT fk_reembolso_devolucion_venta FOREIGN KEY (id_devolucion,id_venta) REFERENCES t_devolucion(id_devolucion,id_venta) ON DELETE RESTRICT,
    CONSTRAINT fk_reembolso_responsable FOREIGN KEY (id_usuario_responsable) REFERENCES t_usuario(id_usuario) ON DELETE RESTRICT,
    CONSTRAINT uq_reembolso_idempotencia UNIQUE (clave_idempotencia), CONSTRAINT uq_reembolso_referencia UNIQUE (id_pago,referencia_externa),
    CONSTRAINT ck_reembolso_estado CHECK (estado IN ('PENDIENTE','APROBADO','RECHAZADO')),
    CONSTRAINT ck_reembolso_monto CHECK (monto > 0),
    CONSTRAINT ck_reembolso_referencia CHECK (referencia_externa IS NULL OR length(trim(referencia_externa)) > 0),
    CONSTRAINT ck_reembolso_aprobacion CHECK (estado <> 'APROBADO' OR fecha_aprobacion IS NOT NULL)
);
CREATE INDEX ix_reembolso_pago_estado ON t_reembolso (id_pago,estado);
CREATE INDEX ix_reembolso_devolucion_created_at ON t_reembolso (id_devolucion,created_at);
CREATE UNIQUE INDEX uq_reembolso_devolucion_pendiente ON t_reembolso (id_devolucion) WHERE estado = 'PENDIENTE';

-- =====================================================
-- REPORTES
-- =====================================================
-- No existen tablas fisicas de reportes; se generan mediante consultas sobre
-- inventario, reservas, ventas, pagos y devoluciones.

