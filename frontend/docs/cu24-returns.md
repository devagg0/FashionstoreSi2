# CU24 — Cancelación y devolución de compras (web)

Implementación exclusivamente frontend. Se conservan los cambios previos del workspace;
no se modifica backend, mobile, migraciones ni Supabase. Sin commit ni push.

## Rutas y componentes

- `/mis-compras/:id`: `PurchasesPage` integra `PurchaseReturnRequest`.
- `/staff/devoluciones` y `/staff/devoluciones/:id`: `StaffReturnsPage`, bajo los
  guards staff y CAJERO. ENCARGADO_SUCURSAL no tiene acceso a CU24 porque el backend no lo autoriza.
- `/admin/devoluciones` y `/admin/devoluciones/:id`: el mismo componente, bajo los
  guards administrativos. El backend exige también asignación activa a la sucursal.
- `ReturnModal`: diálogo responsive, foco inicial, recorrido de foco, Escape y
  restauración de foco al cerrar. No se cierra durante el envío.
- `ReturnsService`: los siete endpoints existentes, Bearer y UUID de idempotencia
  para solicitudes del cliente. No realiza operaciones directas de inventario o pago.

## Cliente

Una compra PENDIENTE sin cancelación activa muestra «Cancelar compra». El contrato
no entrega un indicador adicional de cancelabilidad ni el movimiento de salida;
el backend confirma la elegibilidad al recibir la solicitud. El modal exige motivo
y explica que la cancelación requiere revisión y procesamiento del personal.

Para COMPLETADA, el modal presenta nombre, talla, color, cantidad comprada y selector.
Consulta las solicitudes anteriores no rechazadas para restar sus unidades por variante.
Si esa consulta falla, bloquea el envío hasta poder verificar el cupo. Exige motivo,
cantidades enteras entre cero y el cupo disponible y al menos una unidad seleccionada.
El POST solo incluye motivo y líneas con cantidad positiva.

Se muestra referencia visual `SOL-00007` basada en el ID real (no es un número de
documento fiscal), tipo, estado, motivo, fecha, líneas y reembolsos disponibles.
El historial de CU23 permanece integrado. «Consultar» y «Actualizar estado» usan
GET de la solicitud propia y refrescan el detalle de compra.

Los botones y métodos bloquean doble envío. Ante resultado incierto, el modal conserva
cuerpo y UUID, bloquea edición y permite repetir la misma solicitud. El UUID se guarda
en sessionStorage por usuario y cuerpo para recuperar el mismo intento tras recargar;
se elimina al confirmar éxito. También se permite recuperar la respuesta idempotente
si el intento incierto aparece después en el historial y ya ocupa el cupo solicitado.

## Personal

La bandeja pagina por 20 solicitudes y filtra por estado mediante los parámetros
del backend. No envía filtro de tipo, porque el contrato no lo admite.
El detalle presenta venta, solicitante, motivo, líneas, restitución y reembolsos.
Solo SOLICITADA permite abrir confirmación de aprobación/rechazo; solo APROBADA
permite procesamiento. Se bloquea autorresolución y procesamiento propio en la interfaz,
con verificación definitiva en el backend.

Al aprobar DEVOLUCION se revisan todas las líneas: cantidad_reintegrar entre cero y
cantidad, importe_restitucion no negativo, con máximo de dos decimales y sin superar
el máximo entregado. Cancelación y rechazo no envían líneas. Procesar no modifica
esas cantidades: se utiliza la autorización ya registrada.

## Reembolso y límites del contrato actual

El detalle CU24 entrega el pago original cobrado con id_pago, medio, proveedor,
entorno, estado, monto y moneda. No expone la referencia del PaymentIntent o Checkout.
Todavía no incluye nombres de producto/cliente/sucursal. Se presentan
referencias y avisos de datos no disponibles; si esos datos llegan, se muestran.
No se llaman rutas adicionales ni se inventan datos.

El medio original se obtiene exclusivamente del detalle del backend, sin selector
ni posibilidad de editarlo. MANUAL requiere comprobante/referencia (máximo
255 caracteres) y envía únicamente `referencia_manual`. STRIPE envía `{}` y nunca pide
datos de tarjeta. El backend vuelve a consultar el pago original bajo bloqueo y decide
el proveedor. Si falta el pago original necesario, se impide confirmar y se muestra
un error controlado. Una solicitud sin reembolso pendiente envía `{}`.

Después de aprobar, se recarga el detalle mediante GET antes de habilitar procesamiento.
Si esa recarga falla, las acciones quedan bloqueadas hasta actualizar correctamente.

Corrección del error HTTP 500 de Stripe: los objetos del SDK no son diccionarios y no
admiten `.get()`. CU24 ahora utiliza acceso por clave mediante el lector seguro del
servicio de pagos, también para metadata, Checkout expandido y Refund. Las regresiones
de backend utilizan objetos reales del SDK, sin solicitudes externas.

El resultado de process actualiza el detalle directamente con la respuesta del backend.
PROCESADA muestra confirmación y estado del reembolso. PENDIENTE mantiene el caso
APROBADA; «Reconsultar reembolso» usa process sobre el mismo ID para consultar Stripe,
puesto que GET solo consulta el estado local. RECHAZADO muestra necesidad de conciliación
y bloquea otro procesamiento. «Actualizar» solo recarga los datos locales.

## Estados y errores

Badges SOLICITADA/APROBADA/RECHAZADA/PROCESADA y PENDIENTE/APROBADO/RECHAZADO de reembolso.
Mensajes y estados de carga accesibles; diseño con tokens FashionStore, tarjetas,
resumen lateral y adaptación a pantallas pequeñas.

401 cierra sesión y dirige a login; 403 indica permisos/asignación; 404 oculta recursos
no disponibles. 409/422 muestran el mensaje de negocio si existe (duplicado, compra no
cancelable, cantidades inválidas, solicitud resuelta). Red, timeout, 500 y 503 explican
que el resultado puede ser incierto y permiten reintentar/actualizar sin duplicar operaciones.

## Archivos

Nuevos:

- `src/app/core/services/returns.service.ts` y `.spec.ts`.
- `src/app/pages/purchases/return-request/return-request.ts`, `.html`, `.scss`, `.spec.ts`.
- `src/app/pages/staff/returns/staff-returns.ts`, `.html`, `.scss`, `.spec.ts`.
- `src/app/shared/components/return-modal/return-modal.ts`.
- `docs/cu24-returns.md`.

Modificados:

- `src/app/app.routes.ts`.
- `src/app/core/guards/staff.guard.spec.ts`.
- `src/app/pages/purchases/purchases.ts`, `.html` y `.spec.ts`.
- `src/app/layout/staff-layout/staff-layout.ts`, `.html`, `.spec.ts`.
- `src/app/layout/admin-layout/admin-layout.ts` y `.html`.

## Verificación

Suite: `npm test -- --watch=false`.
Resultado final: **641 pruebas aprobadas en 66 archivos**, incluidas **31 pruebas nuevas de CU24**.
Corrección de pago original: suites completas aprobadas con **752 pruebas backend** y
**644 frontend**. Las pruebas de CU24 backend son 35 y las del detalle staff web son 16.
Incluye pruebas de cancelación pendiente, devoluciones parcial/total, motivo obligatorio,
cantidades inválidas y anteriores, aprobación/rechazo, procesamiento, comprobante manual,
Stripe pendiente/aprobado/fallido, errores API, sesión expirada, autorresolución,
doble clic y reintento con el mismo UUID.

Build de producción: `npm run build`. En este entorno se necesita
`NODE_OPTIONS=--use-system-ca` para verificar el certificado al descargar las fuentes
Google existentes; no se desactiva TLS ni se cambia la configuración del proyecto.
Los avisos de presupuesto corresponden a estilos existentes, sin nuevos avisos de CU24.
Las pruebas simulan el API; no ejecutan reembolsos externos ni prueban Supabase.

Build final aprobado: `dist/frontend/browser`. Bundle inicial: 360,80 kB.
