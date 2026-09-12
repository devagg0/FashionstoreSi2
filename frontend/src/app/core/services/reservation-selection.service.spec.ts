import { TestBed } from '@angular/core/testing';
import { ReservationSelectionService } from './reservation-selection.service';

const item = {
  id_producto: 7,
  id_variante_producto: 9,
  producto: 'Chaqueta',
  imagen_principal: null,
  sku: 'CHA-M-NEG',
  talla: 'M',
  color: 'Negro',
  precio_referencia: '80.00',
  cantidad: 2,
};

const context = {
  id_sucursal: 6,
  nombre_sucursal: 'Equipetrol',
  nombre_ciudad: 'Santa Cruz',
  direccion: 'Av. San Martín',
  hora_apertura: '08:00:00',
  hora_cierre: '20:00:00',
  fecha: '2026-09-13',
  horario: '16:30',
};

describe('ReservationSelectionService CU17', () => {
  let service: ReservationSelectionService;

  beforeEach(() => {
    sessionStorage.clear();
    TestBed.resetTestingModule();
    service = TestBed.inject(ReservationSelectionService);
  });

  afterEach(() => sessionStorage.clear());

  it('keeps several variants in a temporary reservation selection', () => {
    service.start(context, item);
    service.add({ ...item, id_variante_producto: 10, sku: 'CHA-L-NEG', cantidad: 1 });
    expect(service.items().length).toBe(2);
    expect(service.itemCount()).toBe(3);
    expect(service.context()).toEqual(context);
    expect(JSON.parse(sessionStorage.getItem('fashionstore_reservation_selection')!).items).toHaveLength(2);
  });

  it('updates and removes an item', () => {
    service.start(context, item);
    service.updateQuantity(9, 4);
    expect(service.items()[0].cantidad).toBe(4);
    service.remove(9);
    expect(service.items()).toEqual([]);
    expect(service.context()).toBeNull();
  });

  it('merges the same variant instead of duplicating it', () => {
    service.start(context, item);
    service.add({ ...item, cantidad: 1 });
    expect(service.items()).toEqual([{ ...item, cantidad: 3 }]);
  });

  it('the first item fixes context and later items cannot replace it implicitly', () => {
    service.start(context, item);
    service.start({ ...context, id_sucursal: 9 }, { ...item, id_variante_producto: 11 });
    expect(service.context()).toEqual(context);
    expect(service.items()).toEqual([item]);
  });
});
