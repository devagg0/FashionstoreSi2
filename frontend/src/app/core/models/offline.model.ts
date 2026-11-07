/**
 * Modelos e interfaces para PK08 - CU08: Preparar y almacenar información para operación offline en FashionStore (Web Angular PWA).
 */

export interface OfflineBranchData {
  id_sucursal: number;
  id_ciudad: number;
  ciudad?: string | null;
  nombre: string;
  direccion: string;
  telefono?: string | null;
  hora_apertura?: string | null;
  hora_cierre?: string | null;
  estado: boolean;
}

export interface OfflineCategoryData {
  id_categoria: number;
  nombre: string;
  descripcion?: string | null;
  estado: boolean;
}

export interface OfflineSizeData {
  id_talla: number;
  nombre: string;
  descripcion?: string | null;
  estado: boolean;
}

export interface OfflineColorData {
  id_color: number;
  nombre: string;
  codigo_hex?: string | null;
  estado: boolean;
}

export interface OfflineProductImageData {
  id_imagen_producto: number;
  url_imagen: string;
  es_principal: boolean;
}

export interface OfflineProductSizeFacet {
  id_talla: number;
  nombre: string;
}

export interface OfflineProductColorFacet {
  id_color: number;
  nombre: string;
  codigo_hex?: string | null;
}

export interface OfflineCollectionData {
  id_coleccion: number;
  nombre: string;
}

export interface OfflineProductData {
  id_producto: number;
  id_categoria: number;
  categoria?: string | null;
  id_temporada?: number | null;
  temporada?: string | null;
  nombre: string;
  seccion: string;
  descripcion?: string | null;
  descripcion_corta?: string | null;
  precio: string | number;
  precio_base?: string | number | null;
  precio_final?: string | number | null;
  tiene_promocion?: boolean;
  imagen_principal?: string | null;
  imagenes?: string[];
  galeria?: OfflineProductImageData[];
  tallas_disponibles?: OfflineProductSizeFacet[];
  colores_disponibles?: OfflineProductColorFacet[];
  colecciones?: OfflineCollectionData[];
  stock_total_disponible?: number;
  disponible_red?: boolean;
  estado: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface OfflineVariantData {
  id_variante_producto: number;
  id_producto: number;
  id_talla: number;
  talla?: string | null;
  id_color: number;
  color?: string | null;
  color_hex?: string | null;
  sku: string;
  precio?: string | number | null;
  stock_total_disponible?: number;
  disponible_red?: boolean;
  estado: boolean;
}

export interface OfflineStockData {
  id_inventario_sucursal: number;
  id_sucursal: number;
  id_variante_producto: number;
  id_producto?: number | null;
  sku?: string | null;
  id_talla?: number | null;
  talla?: string | null;
  id_color?: number | null;
  color?: string | null;
  color_hex?: string | null;
  nombre_sucursal?: string | null;
  id_ciudad?: number | null;
  nombre_ciudad?: string | null;
  stock_actual: number;
  stock_reservado: number;
  stock_disponible: number;
  stock_minimo: number;
  estado_disponibilidad?: 'DISPONIBLE' | 'AGOTADO' | string | null;
  updated_at: string;
}

export interface OfflineClientData {
  id_cliente: number;
  id_usuario: number;
  nombre: string;
  apellido: string;
  correo?: string | null;
  telefono?: string | null;
}

export interface OfflinePackageMetadata {
  version: string;
  fecha_generacion: string;
  valido_hasta: string;
  vigencia_segundos: number;
  id_empresa: number;
  empresa_codigo: string;
  empresa_nombre: string;
  id_usuario: number;
  usuario_rol: string;
  sucursales_autorizadas_ids: number[];
  suscripcion_activa: boolean;
  funcionalidad_offline: boolean;
  total_sucursales: number;
  total_categorias: number;
  total_productos: number;
  total_variantes: number;
  total_existencias: number;
  total_clientes: number;
}

export interface OfflinePackageResponse {
  success: true;
  message: string;
  metadata: OfflinePackageMetadata;
  sucursales: OfflineBranchData[];
  categorias: OfflineCategoryData[];
  tallas: OfflineSizeData[];
  colores: OfflineColorData[];
  productos: OfflineProductData[];
  variantes: OfflineVariantData[];
  existencias: OfflineStockData[];
  clientes: OfflineClientData[];
}

export interface OfflineStatusResponse {
  success: true;
  id_empresa: number;
  version_actual: string;
  version_solicitada?: string | null;
  vigente: boolean;
  requiere_actualizacion: boolean;
  fecha_generacion: string;
  valido_hasta: string;
  sucursales_autorizadas_ids: number[];
  suscripcion_activa: boolean;
  funcionalidad_offline: boolean;
  message: string;
}

export interface OfflineStoredSummary {
  metadata: OfflinePackageMetadata;
  savedAt: string;
  counts: {
    sucursales: number;
    categorias: number;
    tallas: number;
    colores: number;
    productos: number;
    variantes: number;
    existencias: number;
    clientes: number;
  };
  isExpired: boolean;
  timeRemainingText: string;
}

export interface OfflineBranchStockItem {
  id_sucursal: number;
  nombre_sucursal: string;
  ciudad?: string | null;
  stock_actual: number;
  stock_reservado: number;
  stock_disponible: number;
}

export interface OfflineVariantDetailItem {
  id_variante_producto: number;
  id_producto: number;
  sku: string;
  id_talla?: number;
  id_color?: number;
  talla: string;
  color: string;
  color_hex?: string | null;
  precio: number;
  estado: boolean;
  stockTotalDisponible: number;
  disponibilidadPorSucursal: OfflineBranchStockItem[];
}

export interface OfflineProductDetail {
  producto: OfflineProductData;
  categoriaNombre: string;
  variantes: OfflineVariantDetailItem[];
  totalStockDisponible: number;
  sucursalesConStock: number;
  disponibilidadPorSucursal: OfflineBranchStockItem[];
}

/**
 * Modelos e interfaces para PK08 - CU10: Registrar reserva de prendas offline (Web Angular PWA).
 */

export type OfflineReservationState =
  | 'REGISTRADA_LOCAL'
  | 'ENVIADA'
  | 'PENDIENTE'
  | 'CONFIRMADA'
  | 'ATENDIDA'
  | 'CANCELADA'
  | 'EXPIRADA'
  | 'SINCRONIZADA'
  | 'RECHAZADA'
  | 'EN_CONFLICTO';

export interface OfflineReservationLineItem {
  id_variante_producto: number;
  id_producto: number;
  producto_nombre: string;
  sku: string;
  talla: string;
  color: string;
  precio_referencial: number;
  cantidad: number;
  subtotal: number;
  stock_disponible_estimado: number;
}

export interface OfflineReservationLocal {
  uuid_reserva_offline: string; // crypto.randomUUID()
  codigo_local: string; // Formato RES-LOC-XXXX
  id_reserva?: number;
  codigo_servidor?: string | null;
  id_empresa: number;
  id_usuario: number;
  id_sucursal: number;
  id_cliente?: number | null; // El backend lo resuelve desde la sesión; solo informativo local
  fecha_reserva_offline: string; // ISO string
  fecha_atencion_programada: string; // ISO con zona horaria de Bolivia (horario de recogida)
  fecha_expiracion?: string;
  fecha_atencion?: string | null;
  observaciones?: string | null;
  adelanto_efectivo?: number;
  total_referencial: number;
  saldo_pendiente: number;
  estado: OfflineReservationState; // 'REGISTRADA_LOCAL'
  created_at: string;
  updated_at?: string;
  // Campos descriptivos informativos (sin credenciales)
  sucursal_nombre?: string;
  cliente_nombre?: string;
  cliente_apellido?: string;
  cliente_correo?: string;
  cliente_documento?: string;
  cliente_telefono?: string;
  cantidad_prendas?: number;
  motivo_servidor?: string | null;
  conflictos?: OfflineConflictDetail[];
}

export interface OfflineReservationDetailLocal {
  id_detalle_local?: number; // Clave auto-incremental en IndexedDB
  uuid_reserva_offline: string;
  id_variante_producto: number;
  id_producto: number;
  producto_nombre: string;
  sku: string;
  talla: string;
  color: string;
  cantidad: number;
  precio_referencial: number;
  subtotal: number;
  imagen_principal?: string | null;
}

export interface OfflineSyncQueueItem {
  uuid_operacion: string; // crypto.randomUUID()
  tipo_operacion: 'RESERVA' | 'COMPRA' | 'VENTA' | 'TRANSICION_RESERVA';
  uuid_entidad: string; // uuid_reserva_offline o uuid_venta_offline
  estado:
    | OfflineReservationState
    | OfflinePurchaseState
    | 'SINCRONIZADA'
    | 'CONFLICTO'
    | 'PENDIENTE_SINCRONIZACION';
  payload: any;
  reintentos: number;
  ultimo_error?: string | null;
  conflictos?: OfflineConflictDetail[];
  created_at: string;
  updated_at: string;
}

export interface OfflineReceiptData {
  uuid_reserva_offline: string;
  codigo_local: string;
  id_reserva?: number;
  codigo_servidor?: string | null;
  motivo_servidor?: string | null;
  fecha_registro: string;
  fecha_limite: string;
  sucursal_nombre: string;
  sucursal_direccion?: string;
  cliente_nombre?: string;
  cliente_telefono?: string;
  detalles: OfflineReservationDetailLocal[];
  total_referencial: number;
  adelanto_efectivo: number;
  saldo_pendiente: number;
  observaciones?: string | null;
  estado: OfflineReservationState;
  atendido_por?: string;
}

/**
 * Modelos e interfaces para PK08 - CU11: Registrar venta de contado y compra digital offline (Web Angular PWA - CLIENTE).
 */

export interface OfflineCartItemLocal {
  id_variante_producto: number;
  id_producto: number;
  nombre_producto: string;
  sku: string;
  id_talla?: number;
  talla: string;
  id_color?: number;
  color: string;
  color_hex?: string | null;
  precio_unitario: number;
  cantidad: number;
  subtotal: number;
  imagen_principal?: string | null;
  created_at: string;
  updated_at: string;
}

export type OfflinePurchaseState =
  | 'REGISTRADA_LOCAL'
  | 'PENDIENTE_VALIDACION'
  | 'ENVIADA'
  | 'CONFIRMADA'
  | 'RECHAZADA'
  | 'EN_CONFLICTO';

export interface OfflinePurchaseLocal {
  uuid_venta_offline: string; // crypto.randomUUID()
  numero_venta_local: string; // Formato DIG-LOC-XXXX o VTA-LOC-XXXX
  id_venta_local: number; // Identificador numérico local entero para rutas /compra/:id o /staff/ventas/:id
  id_venta_servidor?: number | null;
  numero_venta_servidor?: string | null;
  id_empresa: number;
  id_usuario: number;
  id_cliente?: number | null;
  id_reserva?: number | null;
  codigo_reserva?: string | null;
  uuid_reserva_offline?: string | null;
  id_sucursal: number;
  canal: 'DIGITAL' | 'PRESENCIAL';
  moneda: 'BOB';
  subtotal: number;
  descuento_total: number;
  total: number;
  medio_pago: 'EFECTIVO' | 'QR' | 'TARJETA';
  pago_simulado: boolean;
  referencia_pago_local: string;
  estado_pago: 'PENDIENTE_VALIDACION' | 'APROBADO';
  estado: OfflinePurchaseState; // 'REGISTRADA_LOCAL'
  fecha_venta_offline: string; // ISO string
  created_at: string;
  updated_at?: string;
  // Campos descriptivos informativos (sin datos sensibles ni tokens bancarios)
  sucursal_nombre?: string;
  sucursal_direccion?: string;
  cliente_nombre?: string;
  cliente_correo?: string;
  cajero_nombre?: string;
  observaciones?: string | null;
  motivo_servidor?: string | null;
  conflictos?: OfflineConflictDetail[];
}

export interface OfflinePurchaseDetailLocal {
  id_detalle_local?: number; // Clave auto-incremental en IndexedDB
  uuid_venta_offline: string;
  id_variante_producto: number;
  id_producto: number;
  producto_nombre: string;
  sku: string;
  id_talla?: number;
  talla: string;
  id_color?: number;
  color: string;
  cantidad: number;
  precio_unitario: number;
  descuento_unitario: number;
  subtotal_linea: number;
}

export interface OfflinePurchaseReceiptData {
  uuid_venta_offline: string;
  numero_venta_local: string;
  id_venta_local: number;
  fecha_registro: string;
  canal?: 'DIGITAL' | 'PRESENCIAL';
  sucursal: {
    id_sucursal: number;
    nombre: string;
    direccion?: string;
  };
  cliente?: {
    nombre: string;
    apellido?: string;
    correo?: string;
  } | null;
  cajero?: {
    id_usuario: number;
    nombre: string;
  } | null;
  detalles: OfflinePurchaseDetailLocal[];
  subtotal: number;
  descuento_total: number;
  total: number;
  moneda: 'BOB';
  medio_pago: 'EFECTIVO' | 'QR' | 'TARJETA';
  pago_simulado: boolean;
  referencia_pago: string;
  estado_venta: 'PENDIENTE' | 'COMPLETADA';
  estado_pago: 'PENDIENTE_VALIDACION' | 'APROBADO';
  comprobante_provisional: true;
  mensaje_advertencia: string;
}

export interface ClientOfflinePurchaseResult {
  success: boolean;
  uuid_venta_offline: string;
  id_venta_local: number;
  numero_venta_local: string;
  receipt: OfflinePurchaseReceiptData | null;
  message: string;
  errors?: string[];
  alreadyStored?: boolean;
}

export interface CashierOfflineSaleInput {
  uuid: string;
  idSucursal: number;
  medioPago: 'EFECTIVO' | 'QR' | 'TARJETA';
  items: {
    id_variante_producto: number;
    cantidad: number;
    precio_unitario?: number;
    descuento_unitario?: number;
    id_producto?: number;
    sku?: string;
  }[];
  idReserva?: number | null;
  idCliente?: number | null;
  observaciones?: string | null;
  now?: Date;
}

export interface CashierOfflineSaleResult {
  success: boolean;
  uuid_venta_offline: string;
  id_venta_local: number;
  numero_venta_local: string;
  receipt: OfflinePurchaseReceiptData | null;
  message: string;
  errors?: string[];
  alreadyStored?: boolean;
}

export function hashReservationUuidToId(uuid: string): number {
  let hash = 0;
  for (let i = 0; i < uuid.length; i++) {
    hash = (Math.imul(31, hash) + uuid.charCodeAt(i)) | 0;
  }
  return 70000000 + (Math.abs(hash) % 9999999);
}

/**
 * Modelos e interfaces para PK08 - CU13: Sincronizar operaciones pendientes de FashionStore (FastAPI, PostgreSQL multitenant).
 */

export type OfflineSyncOperationType = 'RESERVA' | 'COMPRA' | 'VENTA' | 'TRANSICION_RESERVA';

export type OfflineSyncResultStatus =
  | 'CONFIRMADA'
  | 'RECHAZADA'
  | 'EN_CONFLICTO'
  | 'REINTENTABLE';

export type OfflineSyncServerStatus =
  | 'SINCRONIZADA'
  | 'RECHAZADA'
  | 'CONFLICTO'
  | 'PENDIENTE_SINCRONIZACION';

export interface OfflineConflictDetail {
  tipo_conflicto: string;
  codigo_conflicto?: string;
  id_variante_producto?: number | null;
  sku?: string | null;
  valor_esperado?: any;
  valor_actual_servidor?: any;
  corregible?: boolean;
  requiere_consentimiento?: boolean;
  datos_servidor?: any;
  acciones_permitidas?: OfflineResolutionAction[];
  detalle: string;
}

export interface OfflineCodeLinkItem {
  referencia_local: string;
  tipo_operacion: OfflineSyncOperationType;
  id_servidor: number;
  codigo_servidor: string;
}

export interface OfflineSyncOperationInputDto {
  uuid_operacion: string;
  uuid_entidad?: string | null;
  tipo_operacion: OfflineSyncOperationType;
  secuencia?: number | null;
  depende_de_uuid?: string | null;
  codigo_local?: string | null;
  fecha_operacion_offline?: string | null;
  payload?: any;
  datos_originales?: any;
}

export type OfflineQueueSyncOperationInputDto = OfflineSyncOperationInputDto;

export interface OfflineSyncOperationResult {
  uuid_operacion: string;
  uuid_entidad?: string | null;
  tipo_operacion: OfflineSyncOperationType;
  secuencia: number;
  confirmada: boolean;
  estado_resultado: OfflineSyncResultStatus;
  estado_sincronizacion: OfflineSyncServerStatus;
  id_servidor?: number | null;
  codigo_servidor?: string | null;
  codigo_local?: string | null;
  estado_entidad_servidor?: string | null;
  id_pago?: number | null;
  medio_pago?: string | null;
  estado_pago?: string | null;
  pago_simulado?: boolean;
  pendiente_validacion_externa?: boolean;
  subtotal?: number | null;
  descuento_total?: number | null;
  total?: number | null;
  moneda?: string | null;
  id_reserva_asociada?: number | null;
  codigo_reserva_asociada?: string | null;
  id_sucursal?: number | null;
  id_cliente?: number | null;
  id_empleado?: number | null;
  id_usuario?: number | null;
  id_empresa?: number | null;
  reintentable: boolean;
  conservar_en_cola: boolean;
  conflictos?: OfflineConflictDetail[];
  liberaciones_reserva?: any[];
  motivo?: string | null;
  mensaje?: string | null;
  fecha_sincronizacion: string;
  resumen_cu12?: any;
}

export interface OfflineQueueSyncRequest {
  operaciones: OfflineSyncOperationInputDto[];
}

export interface OfflineQueueSyncResponse {
  success: boolean;
  empresa_id: number;
  id_usuario: number;
  rol: string;
  total_operaciones: number;
  confirmadas: number;
  rechazadas: number;
  en_conflicto: number;
  reintentables: number;
  resultados: OfflineSyncOperationResult[];
  resultados_por_uuid: Record<string, OfflineSyncOperationResult>;
  vinculaciones_codigos: Record<string, OfflineCodeLinkItem>;
  fecha_sincronizacion: string;
  mensaje: string;
}

/**
 * Modelos e interfaces para PK08 - CU14: Gestionar conflictos y resultados de sincronización (FastAPI / PostgreSQL multitenant).
 */

export type OfflineResolutionAction =
  | 'REINTENTAR_SIN_CAMBIOS'
  | 'ACEPTAR_PRECIO_SERVIDOR'
  | 'AJUSTAR_CANTIDAD_STOCK'
  | 'QUITAR_PRENDA'
  | 'REPROGRAMAR_HORARIO'
  | 'CAMBIAR_SUCURSAL'
  | 'COMPLETAR_TRANSICIONES_RESERVA'
  | 'CONFIRMAR_Y_ATENDER_RESERVA'
  | 'VINCULAR_OPERACION_EXISTENTE'
  | 'DESCARTAR_OPERACION';

export interface OfflineServerVariantSnapshot {
  id_variante_producto: number;
  id_producto?: number | null;
  sku?: string | null;
  nombre_producto?: string | null;
  activa: boolean;
  stock_actual: number;
  stock_reservado: number;
  stock_disponible: number;
  precio_base_servidor: number | string;
  descuento_unitario_servidor: number | string;
  precio_neto_servidor: number | string;
  id_promocion_activa?: number | null;
  cantidad_solicitada: number;
  precio_capturado_offline?: number | string | null;
}

export interface OfflineServerCurrentData {
  id_sucursal: number;
  sucursal_nombre?: string | null;
  sucursal_activa: boolean;
  hora_apertura_sucursal?: string | null;
  hora_cierre_sucursal?: string | null;
  horarios_sugeridos: string[];
  variantes: OfflineServerVariantSnapshot[];
  subtotal_servidor?: number | null;
  descuento_total_servidor?: number | null;
  total_servidor?: number | null;
  id_reserva_servidor?: number | null;
  codigo_reserva_servidor?: string | null;
  estado_reserva_servidor?: string | null;
  fecha_expiracion_reserva?: string | null;
  id_venta_existente?: number | null;
  numero_venta_existente?: string | null;
  estado_venta_existente?: string | null;
  estado_pago_existente?: string | null;
}

export interface OfflineOperationConflictDiagnosis {
  uuid_operacion: string;
  uuid_entidad?: string | null;
  tipo_operacion: OfflineSyncOperationType;
  secuencia: number;
  depende_de_uuid?: string | null;
  codigo_local?: string | null;
  confirmada_en_servidor: boolean;
  id_servidor?: number | null;
  codigo_servidor?: string | null;
  estado_resultado: OfflineSyncResultStatus;
  estado_sincronizacion: OfflineSyncServerStatus;
  codigo_conflicto_principal?: string | null;
  motivo?: string | null;
  corregible: boolean;
  requiere_consentimiento: boolean;
  bloqueada_por_dependencia: boolean;
  conflictos: OfflineConflictDetail[];
  datos_actuales_servidor: OfflineServerCurrentData;
  acciones_permitidas: OfflineResolutionAction[];
  mensaje: string;
}

export interface OfflineConflictDiagnoseRequest {
  operaciones: OfflineSyncOperationInputDto[];
}

export interface OfflineConflictDiagnoseResponse {
  success: boolean;
  empresa_id: number;
  id_usuario: number;
  rol: string;
  total_diagnosticadas: number;
  ya_sincronizadas: number;
  en_conflicto: number;
  rechazadas: number;
  listas_para_sincronizar: number;
  diagnosticos: OfflineOperationConflictDiagnosis[];
  diagnosticos_por_uuid: Record<string, OfflineOperationConflictDiagnosis>;
  fecha_diagnostico: string;
  mensaje: string;
}

export interface OfflineOperationResolutionInput {
  uuid_operacion: string;
  uuid_entidad?: string | null;
  tipo_operacion: OfflineSyncOperationType;
  secuencia?: number | null;
  depende_de_uuid?: string | null;
  codigo_local?: string | null;
  accion_resolucion: OfflineResolutionAction;
  consentimiento_usuario: boolean;
  nueva_fecha_atencion_programada?: string | null;
  nuevo_id_sucursal?: number | null;
  cantidades_ajustadas?: Record<number, number> | null;
  variantes_excluidas?: number[];
  reserva?: any;
  compra?: any;
  venta?: any;
  transicion?: any;
  payload?: any;
  datos_originales?: any;
}

export interface OfflineOperationResolutionResult {
  uuid_operacion: string;
  uuid_entidad?: string | null;
  tipo_operacion: OfflineSyncOperationType;
  secuencia: number;
  accion_aplicada: OfflineResolutionAction;
  consentimiento_verificado: boolean;
  resuelta: boolean;
  descartada_por_usuario: boolean;
  confirmada: boolean;
  estado_resultado: OfflineSyncResultStatus;
  estado_sincronizacion: OfflineSyncServerStatus;
  id_servidor?: number | null;
  codigo_servidor?: string | null;
  codigo_local?: string | null;
  estado_entidad_servidor?: string | null;
  id_pago?: number | null;
  medio_pago?: string | null;
  estado_pago?: string | null;
  pago_simulado?: boolean;
  pendiente_validacion_externa?: boolean;
  subtotal?: number | null;
  descuento_total?: number | null;
  total?: number | null;
  moneda?: string;
  id_reserva_asociada?: number | null;
  codigo_reserva_asociada?: string | null;
  id_sucursal?: number | null;
  id_usuario: number;
  id_empresa: number;
  reintentable: boolean;
  conservar_en_cola: boolean;
  conflictos?: OfflineConflictDetail[];
  liberaciones_reserva?: any[];
  datos_actuales_servidor?: OfflineServerCurrentData | null;
  acciones_permitidas?: OfflineResolutionAction[];
  motivo?: string | null;
  mensaje: string;
  fecha_resolucion: string;
  resumen_cu12?: any;
  resultado_cu13?: OfflineSyncOperationResult | null;
}

export interface OfflineConflictResolveRequest {
  resoluciones: OfflineOperationResolutionInput[];
}

export interface OfflineConflictResolveResponse {
  success: boolean;
  empresa_id: number;
  id_usuario: number;
  rol: string;
  total_procesadas: number;
  confirmadas: number;
  descartadas: number;
  en_conflicto: number;
  rechazadas: number;
  reintentables: number;
  resultados: OfflineOperationResolutionResult[];
  resultados_por_uuid: Record<string, OfflineOperationResolutionResult>;
  vinculaciones_codigos: Record<string, OfflineCodeLinkItem>;
  fecha_resolucion: string;
  mensaje: string;
}
