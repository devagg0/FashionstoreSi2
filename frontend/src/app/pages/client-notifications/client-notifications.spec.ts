import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ClientNotificationsPage } from './client-notifications';
import {
  ClientNotificationsService,
  NotificationItem,
  NotificationListResponse,
} from '../../core/services/client-notifications.service';

const mockNotificationList: NotificationListResponse = {
  items: [
    {
      id_notificacion: 1,
      usuario_id: 10,
      empresa_id: 1,
      tipo: 'RESERVA_CREADA',
      titulo: 'Reserva registrada con éxito',
      mensaje: 'Tu reserva #RES-001 ha sido creada.',
      referencia_origen: 'RESERVA',
      referencia_id: 101,
      codigo_referencia: 'RES-001',
      leido: false,
      fecha_lectura: null,
      created_at: '2026-11-09T20:00:00Z',
    },
    {
      id_notificacion: 2,
      usuario_id: 10,
      empresa_id: 1,
      tipo: 'COMPRA_CONFIRMADA',
      titulo: 'Compra confirmada',
      mensaje: 'Tu orden #DIG-VTA-001 ha sido confirmada.',
      referencia_origen: 'VENTA',
      referencia_id: 202,
      codigo_referencia: 'DIG-VTA-001',
      leido: true,
      fecha_lectura: '2026-11-09T21:00:00Z',
      created_at: '2026-11-09T20:30:00Z',
    },
  ],
  total: 2,
  no_leidas: 1,
  page: 1,
  page_size: 15,
  total_pages: 1,
};

describe('CU29 - Gestión de Notificaciones para Clientes', () => {
  let fixture: ComponentFixture<ClientNotificationsPage>;
  let component: ClientNotificationsPage;
  let mockNotificationsService: any;

  beforeEach(async () => {
    mockNotificationsService = {
      getNotifications: vi.fn().mockReturnValue(of(mockNotificationList)),
      getUnreadCount: vi.fn().mockReturnValue(of({ no_leidas: 1 })),
      markAsRead: vi.fn().mockImplementation((id: number) => {
        const found = mockNotificationList.items.find((n) => n.id_notificacion === id);
        return of({ ...(found || mockNotificationList.items[0]), leido: true });
      }),
      markAllAsRead: vi.fn().mockReturnValue(of({ success: true, marcadas: 1 })),
    };

    await TestBed.configureTestingModule({
      imports: [ClientNotificationsPage],
      providers: [
        provideRouter([]),
        { provide: ClientNotificationsService, useValue: mockNotificationsService },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(ClientNotificationsPage);
    component = fixture.componentInstance;
  });

  afterEach(() => {
    fixture.destroy();
  });

  it('debe inicializarse y cargar la lista de notificaciones y conteo de no leídas', () => {
    fixture.detectChanges();

    expect(mockNotificationsService.getNotifications).toHaveBeenCalledWith(1, 15, false);
    expect(component.notifications().length).toBe(2);
    expect(component.total()).toBe(2);
    expect(component.unreadCount()).toBe(1);
    expect(component.loading()).toBe(false);
  });

  it('debe filtrar por no leídas al alternar pestaña', () => {
    fixture.detectChanges();

    component.setFilter(true);

    expect(component.filterUnread()).toBe(true);
    expect(mockNotificationsService.getNotifications).toHaveBeenCalledWith(1, 15, true);
  });

  it('debe marcar una notificación como leída y decrementar el contador', () => {
    fixture.detectChanges();

    const unreadItem = component.notifications()[0];
    component.markAsRead(unreadItem);

    expect(mockNotificationsService.markAsRead).toHaveBeenCalledWith(unreadItem.id_notificacion);
    expect(component.notifications()[0].leido).toBe(true);
    expect(component.unreadCount()).toBe(0);
  });

  it('debe marcar todas las notificaciones como leídas', () => {
    fixture.detectChanges();

    component.markAllAsRead();

    expect(mockNotificationsService.markAllAsRead).toHaveBeenCalled();
    expect(component.unreadCount()).toBe(0);
    expect(component.notifications().every((n) => n.leido)).toBe(true);
  });

  it('debe manejar errores de carga adecuadamente', () => {
    mockNotificationsService.getNotifications.mockReturnValue(
      throwError(() => ({ error: { message: 'Error de servidor al cargar notificaciones' } })),
    );

    fixture.detectChanges();
    component.loadNotifications(1);

    expect(component.loading()).toBe(false);
    expect(component.error()).toBe('Error de servidor al cargar notificaciones');
  });
});

