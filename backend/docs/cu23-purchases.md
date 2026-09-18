# CU23 — Consultar compras (backend)

Solo lectura sobre las tablas existentes. No ejecuta DDL, migraciones, Stripe, pagos, reembolsos ni movimientos de inventario. Reutiliza autenticación CLIENTE y consulta de perfil del repositorio existente de reservas/checkout. CU21 `/api/client/sales/{id_venta}` conserva su contrato de venta digital pendiente.

## Endpoints

- `GET /api/client/purchases`: historial del cliente autenticado.
- `GET /api/client/purchases/{id_venta}`: detalle de su compra, DIGITAL o PRESENCIAL, en cualquier estado.

Bearer JWT de cuenta activa con rol CLIENTE. El propietario se resuelve desde id_usuario del token; no se acepta un propietario proporcionado por navegador. Compra ajena e inexistente devuelven el mismo 404. Cuenta sin perfil CLIENTE devuelve 403.

## Historial

Respuesta `{"success":true,"data":{"items":[],"total":0,"limit":20,"offset":0}}`.

Cada compra devuelve id_venta, numero_venta, fecha (fecha_venta), fecha_completada, canal, estado, subtotal, descuento_total, total, moneda, sucursal `{id_sucursal,nombre}` y pago más reciente o null.

Pago incluye solamente id_pago, medio, estado, monto, moneda y fecha_aprobacion. Si hubo varios intentos se elige por created_at descendente e id_pago descendente; no se duplican ventas.

Filtros opcionales: estado PENDIENTE/COMPLETADA/ANULADA y canal DIGITAL/PRESENCIAL. Se combinan. Orden: fecha de venta descendente e id_venta descendente para desempatar. Paginación limit (1–100; defecto 20) y offset (>=0; defecto 0). total cuenta todas las compras propias que cumplen filtros.

## Detalle

Respuesta `{"success":true,"data":{...}}`, con campos del historial y:

- productos: id_detalle_venta, id_variante_producto, nombre, talla, color, cantidad, precio_unitario, descuento_unitario, subtotal_linea.
- pagos: todos los intentos propios, más recientes primero, con los mismos campos públicos del pago resumido.
- devoluciones: id_devolucion, tipo, estado, motivo, fecha, fecha_resolucion, fecha_procesamiento.
- reembolsos: id_reembolso, id_devolucion, id_pago, estado, monto, fecha, fecha_aprobacion.

Importes Decimal se serializan como strings. Precio y descuento provienen de t_detalle_venta y no del precio actual del catálogo. Nombres, talla y color provienen del catálogo actual; no existen snapshots históricos de esos nombres. Se incluyen productos inactivos. Se preserva la línea incluso si falta el catálogo, con campos descriptivos null. Arrays sin registros se devuelven vacíos.

No se exponen referencias Stripe/reembolso, claves de idempotencia, client_secret, responsables, cliente, empleado, movimientos ni datos de tarjeta. Devoluciones y reembolsos usan proyecciones SQLAlchemy Core explícitas del esquema Ciclo 3 ya existente, sin registrar modelos parciales ni consultar información privada.

## Verificación

Desde backend:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_client_purchases -q
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

Tests con SQLite aislado en memoria, autenticación mockeada; nunca conectan Supabase. Verifican permisos, propiedad, precios históricos, pagos, devoluciones/reembolsos, filtros, orden y que las consultas emitan únicamente SELECT sin commit/flush.

Frontend CU23 pendiente: historial paginado, filtros, detalle con productos/importes históricos y estados de pago/devolución/reembolso, estados vacíos/carga/error y control de sesión. No usar el resumen de sessionStorage como fuente del historial.
