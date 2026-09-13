import { HttpClient, HttpHeaders } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { environment } from '../../../environments/environment';
import { SessionService } from './session.service';

export interface SaleRequest {
  id_sucursal: number;
  id_reserva?: number | null;
  items: { id_variante_producto: number; cantidad: number }[];
}
export interface SaleBranch {
  id_sucursal: number;
  nombre: string;
  ciudad: string;
  direccion: string;
  id_empleado_sucursal: number;
}
export interface SaleLine {
  id_variante_producto: number;
  sku: string;
  producto: string;
  talla: string;
  color: string;
  cantidad: number;
  precio_unitario: string;
  descuento_unitario: string;
  id_promocion: number | null;
  subtotal_linea: string;
}
export interface SaleQuote {
  sucursal: SaleBranch;
  id_empleado: number;
  id_cliente: number | null;
  id_reserva: number | null;
  detalles: (SaleLine & { cantidad_disponible: number })[];
  liberaciones: {
    id_variante_producto: number;
    cantidad_reservada: number;
    cantidad_compra: number;
    cantidad_liberar: number;
  }[];
  subtotal: string;
  descuento_total: string;
  total: string;
}
interface SalePerson {
  id_usuario: number;
  nombre: string;
  apellido: string;
}
export interface SaleData {
  id_venta: number;
  numero_venta: string;
  estado: 'PENDIENTE' | 'COMPLETADA' | 'ANULADA';
  id_sucursal: number;
  id_empleado: number;
  id_cliente: number | null;
  id_reserva: number | null;
  sucursal: SaleBranch;
  cajero: SalePerson & { id_empleado: number };
  cliente: (SalePerson & { id_cliente: number }) | null;
  reserva: { id_reserva: number; codigo: string; estado: string } | null;
  fecha_venta: string;
  detalles: SaleLine[];
  subtotal: string;
  descuento_total: string;
  total: string;
  movimiento: {
    id_movimiento_inventario: number;
    id_empleado_sucursal: number;
    tipo_movimiento: 'VENTA';
    estado: 'PENDIENTE' | 'CONFIRMADO' | 'ANULADO';
  };
}
export interface SalesResponse<T> {
  success: true;
  data: T;
}

@Injectable({ providedIn: 'root' })
export class StaffSalesService {
  private readonly http = inject(HttpClient);
  private readonly session = inject(SessionService);
  private readonly url = `${environment.apiUrl}/api/staff/sales`;
  private headers(): HttpHeaders {
    const token = this.session.getAccessToken();
    return token ? new HttpHeaders({ Authorization: `Bearer ${token}` }) : new HttpHeaders();
  }
  getBranches() {
    return this.http.get<SalesResponse<SaleBranch[]>>(`${this.url}/branches`, {
      headers: this.headers(),
    });
  }
  quoteSale(payload: SaleRequest) {
    return this.http.post<SalesResponse<SaleQuote>>(`${this.url}/quote`, payload, {
      headers: this.headers(),
    });
  }
  createSale(payload: SaleRequest, idempotencyKey: string) {
    return this.http.post<SalesResponse<SaleData>>(this.url, payload, {
      headers: this.headers().set('Idempotency-Key', idempotencyKey),
    });
  }
  getSale(idVenta: number) {
    return this.http.get<SalesResponse<SaleData>>(`${this.url}/${idVenta}`, {
      headers: this.headers(),
    });
  }
}
