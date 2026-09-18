# CU23 — Mis compras (web)

Rutas protegidas por clientGuard: /mis-compras y /mis-compras/:id. Ambas usan PurchasesPage con carga perezosa. Acceso desde menú de cuenta CLIENTE en desktop y móvil web. No se modificó backend/mobile ni se realizaron escrituras externas.

ClientPurchasesService consume únicamente GET /api/client/purchases y GET /api/client/purchases/{id_venta}, con Bearer JWT. No usa sessionStorage como fuente del historial, ni envía un id_cliente.

Historial en tarjetas, orden descendente proporcionado por backend. Filtros estado/canal, páginas de 12 y Cargar más. Al filtrar se cancela la solicitud previa y se reinicia paginación. Se conservan tarjetas al fallar la siguiente página; reintentar conserva offset. Carga/doble clic, vacío, filtros sin resultados, errores de red, 401 y 404 tienen estados propios.

Detalle con precios y descuentos históricos, productos, resumen lateral, pagos, devoluciones y reembolsos existentes. No renderiza referencias Stripe, claves ni identificadores técnicos de devoluciones/reembolsos. Los valores faltantes se muestran con texto claro o marcador de imagen. No existen acciones de pago, devolución ni modificación.

Límites del contrato disponible: no entrega imágenes (se usa marcador; se soporta imagen opcional cuando esté disponible), fecha de creación de cada intento de pago (se muestra fecha de aprobación), ni productos/cantidades afectados por devolución (se indica ausencia y no se deduce de productos comprados). Para mostrar esos datos reales hace falta una ampliación futura del contrato backend, fuera de este cambio.

Verificación desde frontend:

```powershell
npm.cmd test -- --watch=false
$env:NODE_OPTIONS = '--use-system-ca'
npm.cmd run build
```

Tests con HTTP mockeado: no conectan Stripe ni Supabase. NODE_OPTIONS habilita certificados del sistema para fuentes HTTPS manteniendo validación TLS.
