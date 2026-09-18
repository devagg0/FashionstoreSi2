import { HttpClient, HttpHeaders } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { environment } from '../../../environments/environment';
import { SessionService } from './session.service';

export interface SaleReceipt {
  numero_venta: string;
  fecha_completada: string;
  canal: 'DIGITAL' | 'PRESENCIAL';
  sucursal: { nombre: string; direccion: string };
  cliente: { nombre: string; apellido: string } | null;
  productos: {
    nombre: string | null; talla: string | null; color: string | null;
    cantidad: number; precio_unitario: string; descuento_unitario: string; subtotal_linea: string;
  }[];
  subtotal: string;
  descuento_total: string;
  total: string;
  moneda: 'BOB';
  pago: { medio: 'TARJETA' | 'EFECTIVO' | 'QR'; estado: 'APROBADO' | 'REEMBOLSADO'; monto: string };
}

@Injectable({ providedIn: 'root' })
export class ReceiptsService {
  private readonly http = inject(HttpClient);
  private readonly session = inject(SessionService);
  get(id: number, audience: 'client' | 'staff') {
    const token = this.session.getAccessToken();
    const headers = new HttpHeaders(token ? { Authorization: `Bearer ${token}` } : {});
    const resource = audience === 'client' ? 'purchases' : 'sales';
    return this.http.get<{ success: true; data: SaleReceipt }>(
      `${environment.apiUrl}/api/${audience}/${resource}/${id}/receipt`, { headers },
    );
  }
}
