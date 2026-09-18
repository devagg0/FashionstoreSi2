# Pago web CU22

Pantalla compartida: `/compra/:id/pago` (CLIENTE) y `/staff/ventas/:id/pago` (CAJERO). Entrar desde compra pendiente o venta registrada.

El resumen de CU20/CU21 se conserva en sessionStorage por usuario y venta. Es solo presentación: el backend determina permisos, importes y estado. UUID, medio e id_pago se guardan antes de continuar y se reutilizan ante errores de red.

DIGITAL ofrece QR y TARJETA. PRESENCIAL ofrece EFECTIVO, QR y TARJETA al CAJERO.

## Tarjeta

Pagar con tarjeta inicia el intento si hace falta, solicita `/stripe/checkout-session` y redirige a la URL HTTPS validada de checkout.stripe.com. FashionStore no pide tarjeta; la captura ocurre exclusivamente en Stripe Checkout TEST. No existen controles de fixtures en la interfaz.

El retorno reconoce checkout=success/cancel y payment_id. Comprueba identificador, intento guardado y pertenencia a venta mediante GET autenticado, luego llama `/stripe/sync`. Ignora session_id como evidencia. Solo el resultado del backend puede mostrar pago aprobado y venta COMPLETADA; success no es prueba de pago. Cancel muestra que la compra continúa pendiente y permite abrir nuevamente la misma sesión. Si el backend confirma que se pagó aun tras cancel, prevalece la confirmación.

## QR y efectivo

Generar QR inicia un pago pendiente y muestra patrón SVG de demostración derivado de id_pago, monto y referencia de operación no sensibles. No es un código bancario ni realiza transferencias. Ya realicé el pago abre el modal y llama `/qr/confirm` sin resultado elegido por cliente. APROBADO muestra comprobante; RECHAZADO conserva venta pendiente y permite nuevo intento sujeto a validaciones del backend.

EFECTIVO sigue exclusivo de CAJERO PRESENCIAL con confirmación del importe recibido y `/manual/confirm`.

## Recuperación y límites

Se bloquean doble envío, cambios de método con intento activo, y pagos a ventas COMPLETADAS/ANULADAS. El estado de carga continúa mientras se redirige a Stripe. Red, timeout, 409 y 503 conservan el mismo intento. Consultar estado recupera el pago local; tarjeta también dispone de sync. Un conflicto no permite descartar un intento pendiente para crear otro.

401 pide iniciar sesión conservando el intento. Sin ID ni UUID guardados no existe búsqueda de pago por venta en el contrato actual: puede recuperarse por ID desde errores. Abrir otra pestaña sin resumen requiere volver a origen. El resumen local no autoriza pagos ni garantiza estado vigente: el backend vuelve a validar cada operación.

## Validación

```powershell
npm.cmd test -- --watch=false
$env:NODE_OPTIONS = '--use-system-ca'
npm.cmd run build
```

NODE_OPTIONS permite usar el almacén de certificados del equipo durante descarga de fuentes, manteniendo TLS verificado. Tests mockean HTTP y navegación; no crean pagos ni conectan a Stripe/Supabase.
