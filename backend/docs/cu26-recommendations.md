# CU26: recomendaciones de prendas

GET `/api/client/recommendations` requiere CLIENTE y perfil `t_cliente` asociado.
Reutiliza `require_client` de CU17 (`ClientDependency`), igual que CU19 y CU23.
Query: `limit` 1..50 (default 12), `id_sucursal` y `id_ciudad` opcionales.
La validacion de sucursal/ciudad reutiliza `CatalogService._validate_location` de
CU12, asi que los codigos de error coinciden con el catalogo publico.

Respuesta: `success: true`, `origen` (`PERSONALIZADO` o `FALLBACK`) y `data` con
id_producto, nombre, descripcion_corta, seccion, categoria, temporada,
precio_base, precio_final, tiene_promocion, promocion, monto_descuento,
porcentaje_descuento, imagen_principal, variante_sugerida (con stock_disponible),
score y motivo. Los importes se serializan como cadenas, igual que CU23 y CU25.
El `score` es informativo: sirve para depurar el orden, no para mostrarlo crudo.

## Algoritmo

Recomendador hibrido en dos fases, sin IA externa, sin embeddings, sin modelos
entrenados y sin estado persistido. Todo se resuelve en memoria sobre un pool
acotado de candidatos.

Fase 0, perfil de afinidad. Una sola consulta con `UNION ALL` de cuatro fuentes
del propio cliente, proyectadas sobre los atributos de la prenda: compras
COMPLETADAS (5.0), reservas ATENDIDA/CONFIRMADA (3.0), carrito ACTIVO (1.5) y
carrito ABANDONADO (0.6). Cada senal se multiplica por su antiguedad
(<=30d 1.0, <=90d 0.7, <=180d 0.45, resto 0.25) y por las unidades con tope de 5,
para que una compra masiva no domine el perfil. Se agregan afinidades por
categoria, talla, color, seccion, temporada y por el par (categoria, seccion)
que materializa los "productos relacionados". Cada dimension se normaliza a
0..1 contra el maximo del propio cliente. Ventana de historial: 365 dias.

Fase 1, pool y puntaje base. El pool exige producto activo, variante activa y
stock disponible (`stock_actual - stock_reservado > 0`) en sucursal activa, con
`ORDER BY` que prioriza categoria afin, temporada afin, promocion vigente y
popularidad antes del `LIMIT`, de modo que el recorte no descarte candidatos
relevantes. Sobre esas filas se calcula el puntaje sin talla/color.

Fase 2, variantes y presentacion. Se recorta a `max(24, limit * 4)` candidatos y
solo para ellos se piden variantes con stock e imagenes, en dos consultas por
lote. Ahi se suma el termino de talla/color y se elige la `variante_sugerida`:
la de mayor afinidad talla+color y, a igualdad, la de mas stock.

Orden final: lo ya comprado se relega al final de la lista en lugar de
eliminarse, para evitarlo "cuando sea posible" sin sacrificar el `limit`
solicitado. El desempate es por `id_producto`, asi que el orden es determinista.

## Pesos

Personalizado (suman 1.0): categoria 0.28, talla 0.12, color 0.08, seccion 0.08,
temporada 0.08, relacionado 0.06, popularidad 0.20, promocion 0.06, novedad 0.04.

Fallback de cliente sin historial (suman 1.0): popularidad 0.45, promocion 0.25,
vigencia de temporada/coleccion 0.20, novedad 0.10.

Como los pesos personalizados ya incluyen popularidad, promocion y novedad, un
cliente con historial parcial degrada de forma continua: no hay una rama
especial para "solo carrito". El fallback se activa unicamente cuando el perfil
queda completamente vacio.

El `motivo` se deriva del termino dominante del puntaje: la categoria se traduce
al origen que mas peso aporto ("Basado en tus compras", "Porque reservaste
prendas similares", "Por lo que tienes en tu carrito"), y el resto usa un texto
fijo ("Disponible en tu talla habitual", "En tu color favorito",
"Popular entre clientes similares", "En promocion vigente", ...).

## Datos y rendimiento

Tablas leidas, todas preexistentes: t_cliente, t_venta, t_detalle_venta,
t_reserva, t_detalle_reserva, t_carrito, t_detalle_carrito, t_producto,
t_variante_producto, t_categoria, t_talla, t_color, t_temporada, t_coleccion,
t_producto_coleccion, t_imagen_producto, t_inventario_sucursal, t_sucursal,
t_promocion y t_promocion_producto.

Presupuesto de consultas: 7 por request (perfil de cliente, senales, popularidad,
promociones vigentes, pool, variantes del top e imagenes del top), mas 1 por cada
filtro de ubicacion que haya que validar, o sea 9 en el peor caso. Todas son por
lote y estan acotadas por `LIMIT` o por ventana de fechas. Ninguna se ejecuta
por producto: el numero de consultas no crece con el tamano del catalogo y hay
una prueba que lo fija.
La imagen principal y las promociones del top se piden en un solo `IN`, no una
por producto. La popularidad se limita a 90 dias y 120 productos; las
promociones vigentes a 500 filas; el pool a `min(200, max(60, limit * 16))`.

No se usa `greatest()` ni aritmetica de fechas en SQL: el descuento y el
decaimiento se calculan en Python. Eso mantiene una sola sentencia valida tanto
en PostgreSQL como en el SQLite de las pruebas, y evita duplicar la logica de
precio por dialecto. El calculo del mejor descuento compara el precio final real
porque un 10% y un monto fijo de Bs 20 no son comparables por su valor nominal.

Solo SELECT: sin commit, flush, bloqueos, escrituras, tablas nuevas ni
migraciones. Una prueba falla si aparece un INSERT/UPDATE/DELETE o si se invoca
`commit`/`flush`.

Notas de exactitud conocidas: una venta PRESENCIAL sin `id_cliente` no alimenta
el perfil, porque `t_venta.id_cliente` es nulable y solo el canal DIGITAL lo
exige. El perfil no filtra producto/variante activos a proposito: una prenda
descatalogada sigue revelando la talla, el color y la categoria del cliente.

## Pendiente de frontend

Consumir el endpoint desde Angular y Flutter con el mismo contrato, mostrar
`motivo` como etiqueta de la tarjeta, usar `variante_sugerida` para el boton de
agregar al carrito de CU19, respetar `origen` para diferenciar la vitrina
personalizada de la de bienvenida, y manejar 401/403/404/422/500. No mostrar
`score` al cliente.
