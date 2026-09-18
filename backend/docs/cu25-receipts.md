# CU25: comprobante de venta

GET `/api/client/purchases/{id_venta}/receipt` requiere CLIENTE y propiedad de la venta.
GET `/api/staff/sales/{id_venta}/receipt` reutiliza la autenticacion del personal
CAJERO / ENCARGADO_SUCURSAL y exige empleado con asignacion activa a la sucursal activa.
No se requiere que el empleado consultante sea quien realizo la venta.

Respuesta: `success: true`, `data` con numero_venta, fecha_completada, canal,
sucursal (nombre, direccion), cliente (nombre, apellido) o null, productos
(nombre, talla, color, cantidad, precio_unitario, descuento_unitario, subtotal_linea),
subtotal, descuento_total, total, moneda BOB y pago (medio, estado, monto).
Importes decimales se serializan como cadenas; los importes se toman de la venta
y sus detalles, nunca del precio actual del catalogo. Los nombres, talla y color
proceden del catalogo existente: no hay snapshots historicos de esos textos.

Solo COMPLETADA con fecha_completada y un pago cobrado del mismo importe/moneda.
Un pago REEMBOLSADO fue aprobado previamente y conserva el comprobante historico
con su estado actual; no se descuentan devoluciones del total original.
PENDIENTE/ANULADA, ausencia de pago aprobado o inconsistencias del pago: 409.
Venta inexistente, ajena o fuera de la sucursal autorizada: el mismo 404.
Perfil CLIENTE inexistente o rol incorrecto: 403; sesion invalida/ausente: 401;
identificador invalido: 422. Fallos internos: 500 con mensaje publico generico.

Generacion en memoria mediante SELECT, sin persistencia, numeracion adicional,
llamadas Stripe, cambios de venta/pago/inventario, tablas, migraciones ni PDF.
numero_venta es la unica referencia del comprobante. No se publican referencias
externas del proveedor, claves de idempotencia, secretos ni identificadores internos.

Frontend pendiente: presentar el comprobante en compras y ventas autorizadas,
manejar 401/403/404/409 y ofrecer impresion desde el JSON si se desea.
