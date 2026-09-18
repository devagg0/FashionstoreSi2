# CU25: comprobante web

Rutas: /mis-compras/:id/comprobante (clientGuard) y
/staff/ventas/:id/comprobante (staffGuard y staffChildGuard del panel).
Componente compartido ReceiptPage con audiencia staff declarada en los datos
de ruta. ReceiptsService realiza exclusivamente GET autenticados a los endpoints
CU25 correspondientes; la autorizacion definitiva pertenece al backend.

Mis compras ofrece Ver comprobante para COMPLETADA con fecha y pago
APROBADO/REEMBOLSADO del importe de la venta. No hay indicador de disponibilidad
en el contrato de compras: el endpoint receipt confirma disponibilidad y muestra
el error 409 de forma controlada si falta informacion valida.
El resumen existente de venta staff y la pantalla de pago completado enlazan
al comprobante. No se crean endpoints, ni se modifican pagos o inventario.

Vista comercial con numero completo, fecha en America/La_Paz, sucursal, cliente
opcional, productos y descuentos por unidad, resumen historico en BOB y pago.
No se renderizan campos adicionales ni referencias externas de la respuesta.
Tabla en desktop e impresion; lista adaptada en movil. Sin generacion PDF.

window.print() y @media print/@page A4 imprimen unicamente sale-receipt;
los estilos globales quitan navegacion y espacios del layout solo cuando existe
el comprobante. La comprobacion automatizada verifica la accion window.print;
la paginacion fisica depende del navegador y requiere previsualizacion manual.

Loading bloquea impresion. 401 ofrece login; 403/404/409 explican acceso o
disponibilidad; red/timeout/5xx ofrecen reintento. No se muestran mensajes internos
de API. Se cancelan solicitudes antiguas al cambiar de venta o destruir la vista.
