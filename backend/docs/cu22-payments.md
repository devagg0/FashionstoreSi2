# CU22: gestionar pago (backend TEST)

Usa las tablas existentes del Ciclo 3, sin nuevas migraciones. Todos los endpoints requieren Bearer JWT activo. CLIENTE opera solo sobre su venta DIGITAL; CAJERO, sobre ventas PRESENCIALES de sus sucursales activas. El importe y moneda provienen de la venta.

## API

| Metodo | Endpoint | Entrada |
| --- | --- | --- |
| POST | `/api/sales/{id_venta}/payments` | `{"medio":"EFECTIVO"}` / `QR` / `TARJETA`; header `Idempotency-Key` UUID |
| GET | `/api/payments/{id_pago}` | Estado local |
| POST | `/api/payments/{id_pago}/manual/confirm` | CAJERO PRESENCIAL: `{"resultado":"APROBADO"}` / `RECHAZADO` |
| POST | `/api/payments/{id_pago}/qr/confirm` | Sin body o `{}`; resultado decidido por servidor |
| POST | `/api/payments/{id_pago}/stripe/checkout-session` | Sin body o `{}`; crea o reutiliza Checkout TEST |
| POST | `/api/payments/{id_pago}/stripe/sync` | Sin body o `{}`; consulta Stripe y concilia |

Checkout devuelve `{"success":true,"data":{"payment":{...},"session_id":"cs_test_...","url":"https://checkout.stripe.com/..."}}`. Los otros endpoints devuelven `{"success":true,"data":{...}}` con pago y estado_venta. HTTP 200 con PENDIENTE no significa aprobacion. Los endpoints sin campos rechazan resultados, referencias y URLs enviados por el cliente. Nunca se devuelven claves API ni client_secret.

## EFECTIVO y QR

EFECTIVO permanece solo PRESENCIAL, MANUAL/LOCAL y confirmado por CAJERO. QR permite PRESENCIAL y DIGITAL, MANUAL/LOCAL, sin banco real. Para DIGITAL se utiliza `/qr/confirm`; el cliente no envia APROBADO. `QR_SIMULATION_RESULT` configura la simulacion en el servidor: APROBADO por defecto o RECHAZADO. Un rechazo conserva venta PENDIENTE y stock. La confirmacion manual presencial del CAJERO sigue disponible para QR.

## Stripe Checkout TEST

Iniciar TARJETA solo persiste pago PENDIENTE. `/stripe/checkout-session` crea `mode=payment`, solo tarjeta, con importe exacto en centavos y moneda de venta. Guarda `cs_test_...` en referencia_externa, sin nueva columna. Metadata id_venta, id_pago y clave_idempotencia se incluyen tanto en sesion como en PaymentIntent. Stripe aloja la captura de tarjeta: el backend no recibe ni almacena numero, CVC ni vencimiento.

`STRIPE_CHECKOUT_RETURN_BASE_URL` configura el origen web; defecto `http://localhost:4201`. Permite HTTPS o HTTP solo en localhost, sin credenciales, query, fragmento ni ruta adicional. El backend construye las URLs. DIGITAL retorna a `/compra/{id_venta}/pago`; PRESENCIAL a `/staff/ventas/{id_venta}/pago`. Ambos incluyen payment_id; success agrega `checkout=success&session_id={CHECKOUT_SESSION_ID}` y cancel agrega `checkout=cancel`. Esos parametros no autorizan aprobacion.

Al retornar llamar `/stripe/sync`. El backend recupera Stripe mediante referencia persistida y valida livemode=false, identificacion TEST, mode, importe, moneda, client_reference_id y metadata. Solo aprueba con payment_status=paid, sesion complete y PaymentIntent TEST succeeded con importe recibido, moneda y metadata coincidentes. Mientras no este pagado conserva PENDIENTE; sesion expirada registra EXPIRADO. Cancelar el retorno o rechazar tarjeta dentro de Checkout no habilita otro intento mientras la sesion siga abierta.

Se retiro `/stripe/confirm-test`. Fixtures pm_card_visa / pm_card_chargeDeclined existen solo en pruebas automatizadas. Pagos anteriores pi_... siguen conciliandose mediante sync. Antes de reemplazar un PI antiguo por Checkout se cancela y verifica su cierre; un PI aprobado o en procesamiento bloquea otra sesion y requiere conciliacion.

## Idempotencia e inventario

Reutilizar UUID e id_pago ante doble clic o fallo de red. La misma clave con otra venta/medio retorna 409. Otro intento se bloquea mientras exista pendiente/aprobado. Checkout usa una clave Stripe estable por intento y recupera sesion existente. Repetir sync aprobado no cobra ni descuenta otra vez. COMPLETADA/ANULADA no aceptan nuevo pago; RECHAZADO admite nuevo UUID.

No existe atomicidad entre PostgreSQL y Stripe. Ante resultado remoto incierto se conserva PENDIENTE y se reintenta el mismo pago. Un rollback al persistir referencia reutiliza la clave Stripe. Creacion sin referencia de mas de 23 horas requiere conciliacion operativa para evitar recrearla tras caducar la idempotencia Stripe. No hay webhook ni tarea programada: sync es explicito.

Venta, pago e inventario se bloquean en orden. APROBADO, COMPLETADA, fecha_completada, stock_comprometido=false, movimiento VENTA CONFIRMADO y stocks se guardan en una transaccion local. Rollback revierte todos esos cambios. DIGITAL descuenta unidades compradas de stock_actual y libera exactamente las comprometidas por CU21 en stock_reservado. PRESENCIAL conserva CU20: con reserva libera solo unidades compradas aun retenidas y confirma movimiento pendiente. Conserva reservas ajenas.

El plazo DIGITAL vencido impide iniciar Checkout. Si sync encuentra sesion abierta no pagada de venta vencida, la expira en Stripe antes de registrar EXPIRADO; si falla conserva PENDIENTE. Una aprobacion remota ya obtenida puede conciliarse si compromiso e inventario siguen validos. Liberar compromisos por expiracion de venta queda fuera de este cambio; nunca se libera stock mientras exista sesion cobrable abierta.

## Validacion y siguiente cambio web

Desde backend:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_checkout_payments tests.test_payments tests.test_stripe_service -q
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
.\.venv\Scripts\python.exe -m pip check
```

Las pruebas usan SQLite en memoria y Stripe mockeado. No crean cobros externos ni conectan a Supabase. Modo y claves permanecen exclusivamente TEST.

Frontend pendiente: ofrecer QR DIGITAL y llamar qr/confirm; iniciar TARJETA, solicitar Checkout y redirigir a data.url; retirar botones de fixtures; conservar UUID/id_pago y gestionar retorno success/cancel consultando sync antes de mostrar APROBADO. Reintentar sesion existente ante cancelacion y manejar 409/503 sin generar otro intento incierto.
