/**
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

export interface OfflineProductData {
  id_producto: number;
  id_categoria: number;
  categoria?: string | null;
  id_temporada?: number | null;
  nombre: string;
  seccion: string;
  descripcion?: string | null;
  precio: string | number;
  imagen_principal?: string | null;
  imagenes?: string[];
  estado: boolean;
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
  estado: boolean;
}

export interface OfflineStockData {
  id_inventario_sucursal: number;
  id_sucursal: number;
  id_variante_producto: number;
  id_producto?: number | null;
  stock_actual: number;
  stock_reservado: number;
  stock_disponible: number;
  stock_minimo: number;
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
  | 'CONFIRMADA'
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
  id_empresa: number;
  id_usuario: number;
  id_sucursal: number;
  id_cliente: number;
  fecha_reserva_offline: string; // ISO string
  fecha_atencion_programada: string; // ISO string (límite de retiro)
  observaciones?: string | null;
  adelanto_efectivo?: number;
  total_referencial: number;
  saldo_pendiente: number;
  estado: OfflineReservationState; // 'REGISTRADA_LOCAL'
  created_at: string;
  // Campos descriptivos informativos (sin credenciales)
  sucursal_nombre?: string;
  cliente_nombre?: string;
  cliente_documento?: string;
  cliente_telefono?: string;
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
}

export interface OfflineSyncQueueItem {
  uuid_operacion: string; // crypto.randomUUID()
  tipo_operacion: 'RESERVA';
  uuid_entidad: string; // uuid_reserva_offline
  estado: OfflineReservationState; // 'REGISTRADA_LOCAL'
  payload: {
    uuid_reserva_offline: string;
    id_sucursal: number;
    id_cliente: number;
    fecha_reserva_offline: string;
    fecha_atencion_programada: string;
    detalles: {
      id_variante_producto: number;
      cantidad: number;
      precio_referencial: number;
    }[];
    observaciones?: string | null;
  };
  reintentos: number;
  ultimo_error?: string | null;
  created_at: string;
  updated_at: string;
}

export interface OfflineReceiptData {
  uuid_reserva_offline: string;
  codigo_local: string;
  fecha_registro: string;
  fecha_limite: string;
  sucursal_nombre: string;
  sucursal_direccion?: string;
  cliente_nombre: string;
  cliente_telefono?: string;
  detalles: OfflineReservationDetailLocal[];
  total_referencial: number;
  adelanto_efectivo: number;
  saldo_pendiente: number;
  observaciones?: string | null;
  estado: OfflineReservationState;
  atendido_por: string;
}


