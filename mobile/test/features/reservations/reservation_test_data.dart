import 'package:mobile/features/catalog/catalog_models.dart';
import 'package:mobile/features/reservations/reservation_models.dart';

ReservationDetail reservationDetail({
  ReservationState state = ReservationState.pendiente,
  bool cancelable = true,
  int id = 9,
}) => ReservationDetail(
  id: id,
  code: 'RSV-20260913-ABC123',
  state: state,
  createdAt: DateTime.utc(2026, 9, 13, 12),
  scheduledAt: DateTime.utc(2026, 9, 14, 18),
  expiresAt: DateTime.utc(2026, 9, 14, 19),
  branch: const ReservationBranch(
    id: 1,
    name: 'Sucursal Centro',
    address: 'Av. Principal 100',
    cityId: 2,
    cityName: 'La Paz',
  ),
  garmentCount: 3,
  total: 260,
  cancelable: cancelable,
  items: const [
    ReservationItem(
      variantId: 90,
      sku: 'CHA-NEG-M',
      productId: 10,
      productName: 'Chaqueta urbana',
      imageUrl: null,
      size: CatalogSize(id: 2, name: 'M'),
      color: CatalogColor(id: 4, name: 'Negro', hexCode: '#111111'),
      quantity: 2,
      unitPrice: 80,
      subtotal: 160,
    ),
    ReservationItem(
      variantId: 92,
      sku: 'CAM-ROJ-S',
      productId: 11,
      productName: 'Camisa clásica',
      imageUrl: null,
      size: CatalogSize(id: 1, name: 'S'),
      color: CatalogColor(id: 5, name: 'Rojo', hexCode: '#AA1111'),
      quantity: 1,
      unitPrice: 100,
      subtotal: 100,
    ),
  ],
);

Map<String, dynamic> reservationJson({
  String state = 'PENDIENTE',
  bool cancelable = true,
}) => {
  'id_reserva': 9,
  'codigo': 'RSV-20260913-ABC123',
  'estado': state,
  'created_at': '2026-09-13T12:00:00',
  'fecha_atencion_programada': '2026-09-14T18:00:00',
  'fecha_expiracion': '2026-09-14T19:00:00',
  'sucursal': {
    'id_sucursal': 1,
    'nombre': 'Sucursal Centro',
    'direccion': 'Av. Principal 100',
    'ciudad': {'id_ciudad': 2, 'nombre': 'La Paz'},
  },
  'cantidad_prendas': 3,
  'total': '260.00',
  'cancelable': cancelable,
  'items': [
    {
      'id_variante_producto': 90,
      'sku': 'CHA-NEG-M',
      'id_producto': 10,
      'producto': 'Chaqueta urbana',
      'imagen_principal': null,
      'talla': {'id_talla': 2, 'nombre': 'M'},
      'color': {'id_color': 4, 'nombre': 'Negro', 'codigo_hex': '#111111'},
      'cantidad': 2,
      'precio_unitario': '80.00',
      'subtotal': '160.00',
    },
  ],
};
