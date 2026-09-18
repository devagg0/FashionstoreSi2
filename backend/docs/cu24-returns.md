# CU24 ? Cancelaciones, devoluciones y reembolsos

Implementacion exclusivamente backend sobre las tablas existentes del Ciclo 3.
No ejecuta migraciones, DDL ni modificaciones manuales en Supabase.

## API

Todas las rutas requieren Bearer de una cuenta activa. Las solicitudes POST del cliente
requieren `Idempotency-Key` UUID; repetir la clave y el mismo cuerpo recupera la solicitud.
La misma clave con otro cuerpo devuelve 409. Respuestas: `success`, `data`.

| Metodo | Ruta | Acceso / cuerpo |
|---|---|---|
| POST | /api/client/purchases/{id_venta}/cancellation | CLIENTE propietario; motivo |
| POST | /api/client/purchases/{id_venta}/returns | CLIENTE propietario; motivo, lineas [{id_detalle_venta, cantidad}] |
| GET | /api/client/returns/{id_devolucion} | CLIENTE propietario |
| GET | /api/staff/returns | CAJERO/ADMINISTRADOR; estado opcional, limit (1?100), offset |
| GET | /api/staff/returns/{id_devolucion} | Personal de la sucursal |
| POST | /api/staff/returns/{id_devolucion}/review | resultado APROBADA/RECHAZADA; lineas para aprobar devolucion |
| POST | /api/staff/returns/{id_devolucion}/process | referencia_manual para EFECTIVO/QR; {} para Stripe |

Una linea de revision contiene `id_variante_producto`, `cantidad_reintegrar`,
`importe_restitucion`. Deben revisarse todas las lineas una vez. Cancelaciones y
rechazos no admiten lineas. No se acepta sobrescribir importes, estados o proveedores
mediante campos adicionales en las solicitudes del cliente.

## Cancelacion

Solo venta PENDIENTE sin salida fisica CONFIRMADA. Se registra CANCELACION SOLICITADA.
El personal aprueba o rechaza; nadie resuelve ni procesa su propia solicitud.
Al procesar: cerrar pagos pendientes (expirar Checkout/cancelar PI TEST verificable),
liberar las cantidades comprometidas, anular el movimiento VENTA pendiente existente
y pasar venta a ANULADA. Nunca se crea ENTRADA para cancelacion.
Si hay un pago APROBADO se prepara el reembolso completo al aprobar y se procesa con
el mismo mecanismo de las devoluciones. La venta se anula al finalizar el procesamiento.
Si el pago se completa durante la revision, la cancelacion ya no puede procesarse:
corresponde una devolucion de venta COMPLETADA.

## Devolucion

Solo COMPLETADA. Las lineas corresponden a detalles de esa venta. Cantidades positivas,
sin repetir lineas, limitadas a comprado menos solicitudes SOLICITADAS/APROBADAS/PROCESADAS.
Las RECHAZADAS liberan ese cupo. Se rechaza otra solicitud activa con las mismas lineas
y cantidades aun si quedaran unidades. Se admiten devoluciones parciales sucesivas
tras procesar las anteriores. La idempotencia admite repetir la solicitud original.
El servidor calcula importe maximo incluyendo descuentos y distribuyendo centavos;
el personal puede reducir importe y decidir cantidad_reintegrar entre cero y cantidad.
Al procesar, solo cantidad_reintegrar incrementa stock_actual. Se registra una ENTRADA
CONFIRMADA con responsable de sucursal, enlazada por t_devolucion; su id_venta es NULL
conforme a las restricciones existentes. No hay entrada si el reintegro es cero.
No se altera el historial de la venta COMPLETADA ni se borran ventas o pagos.

## Reembolso y transacciones

El detalle CU24 entrega `pago` con id_pago, medio, proveedor, entorno, estado, monto
y moneda del pago original APROBADO (o REEMBOLSADO para conservar la consulta histórica).
No entrega referencias Stripe ni claves del pago. La operación vuelve a consultar ese
pago bajo bloqueo; el frontend no puede elegir o sobrescribir su medio/proveedor/entorno.
La ausencia de pago aprobado cuando corresponde reembolso devuelve 409 explícito.

Los objetos reales del SDK Stripe no admiten `.get()`: CU24 usa el lector seguro por
clave para PaymentIntent, metadata, Checkout expandido y Refund, evitando el HTTP 500
que antes quedaba oculto detrás del mensaje genérico del frontend.

Refund no contiene `livemode`: CU24 verifica TEST en Checkout/PaymentIntent y Charge.
Antes de crear un Refund consulta el cargo y todos los reembolsos del PaymentIntent,
incluida paginación. Valida identidad, vínculo con PaymentIntent y Charge, importe,
moneda y estado. Solo `succeeded` permite completar el procesamiento local.

Los nuevos Refund incluyen metadata con id_reembolso y clave_idempotencia, para
recuperar su atribución tras un fallo local. La recuperación de registros antiguos
sin metadata solo es automática para un único Refund succeeded por el importe total
del pago, con amount_refunded total y sin otra autorización local competidora.
Un Refund reclamado por otro registro local nunca se reutiliza. Los casos ambiguos
se bloquean sin crear otro Refund. Los reembolsos parciales anteriores correctamente
conciliados se verifican contra sus registros locales y permiten devolver el saldo.

Stripe y PostgreSQL no comparten transacción: succeeded remoto → fallo local →
reintento → consulta de Stripe → conciliación del registro PENDIENTE existente →
finalización local. Se guarda la referencia real, APROBADO y fecha_aprobacion tomada
de `created` de Stripe. El reintegro, movimiento y estado PROCESADA se confirman
atómicamente. Repetir process sobre PROCESADA devuelve el resultado sin nuevas
operaciones de Stripe, stock ni movimientos.

Recuperación verificada de venta 11 / devolución 2 / pago 9 / reembolso local 1:
se vinculó el Refund TEST existente succeeded por Bs 199,90. El servicio dejó
reembolso APROBADO, pago REEMBOLSADO y devolución PROCESADA, con ENTRADA CONFIRMADA 16
por una unidad autorizada. Un segundo process conservó stock y movimiento. La ejecución
utilizó un adaptador que prohíbe crear nuevos Refunds; Stripe solo recibió lecturas.

Regresiones actualizadas sin inventar livemode en Refund: recuperación total legacy,
recuperación parcial por metadata tras rollback, segundo reintento idempotente,
atribución ambigua bloqueada, cargo live bloqueado, creación normal y devolución
parcial posterior con reembolsos anteriores conciliados. Pruebas de Stripe/CU22
y CU24: 133 aprobadas; suite backend completa: 757 aprobadas. Todos los tests
utilizan Stripe simulado y bases locales, sin crear Refunds externos.

Al aprobar se persiste un unico reembolso PENDIENTE con clave UUID estable antes de
cualquier solicitud remota. Se limita por importe autorizado y saldo del pago, contando
reembolsos pendientes y aprobados de otras solicitudes. El pago pasa a REEMBOLSADO
solo cuando la suma de reembolsos APROBADOS alcanza el monto pagado.
Stripe reutiliza el adaptador TEST existente y verifica pago, metadata, moneda, monto,
referencia y livemode=false. Checkout se resuelve a su PaymentIntent.
Se consulta el mismo reembolso si ya hay referencia. Pending/requires_action mantienen
solicitud APROBADA sin reintegro; succeeded completa. Failed/canceled se registran
RECHAZADOS y requieren conciliacion operativa, sin crear un segundo reembolso.
Ante timeout o rollback posterior al resultado remoto se conserva la intencion aprobada
y se reintenta la misma clave. Tras 23 horas sin referencia se bloquea recreacion para
evitar duplicados cuando Stripe expire la idempotencia: requiere conciliacion externa.
No existe una transaccion distribuida con Stripe.

EFECTIVO/QR MANUAL LOCAL requiere comprobante `referencia_manual` ingresado por personal;
registra ejecucion manual, no realiza transferencias bancarias. La referencia no puede
reutilizarse para el mismo pago. Repetir process sobre PROCESADA devuelve el resultado
sin reintegrar ni reembolsar de nuevo.

Bloqueos FOR UPDATE serializan por venta, devolucion, pagos/reembolsos e inventarios
ordenados por variante. El inventario se valida antes del reembolso remoto.
Todo cambio local de procesamiento se confirma en una transaccion o se revierte.
Personal CAJERO/ADMINISTRADOR necesita empleado y asignacion activa a la sucursal,
incluidos administradores. Compras ajenas responden 404. Listado filtra por sucursales.

## Verificacion

Desde backend: `.venv/Scripts/python.exe -m unittest discover -s tests -t .`
Resultado: 746 pruebas aprobadas, incluidas 29 pruebas nuevas de CU24.
Tests con SQLite local, autoflush=False como produccion, y Stripe mockeado;
no realizan cobros/reembolsos externos.
Los tests existentes y CU24 comprueban reglas y rollback; compilacion SQL verifica
FOR UPDATE PostgreSQL. No equivalen a una prueba de concurrencia sobre PostgreSQL real.

Referencia Stripe: https://docs.stripe.com/api/refunds/create y
https://docs.stripe.com/api/refunds/object.

## Pendiente para frontend

Formulario de cancelacion/devolucion y seleccion de cantidades, UUID estable por intento,
consulta de solicitudes, bandeja del personal, revision por linea, comprobantes manuales,
procesamiento/reconsulta de Stripe pendiente y manejo de errores 404/409/422/503.
CU23 ya permite consultar devoluciones/reembolsos desde el detalle de compra.
