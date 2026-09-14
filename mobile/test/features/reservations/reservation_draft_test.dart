import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/features/catalog/catalog_models.dart';
import 'package:mobile/features/reservations/reservation_draft.dart';

void main() {
  test(
    'primera prenda fija contexto y segunda lo conserva en un único body',
    () {
      final draft = ReservationDraftController();
      addTearDown(draft.dispose);

      expect(draft.start(_context, _item(90, quantity: 2)), isTrue);
      expect(draft.add(_item(92)), isTrue);

      expect(draft.context, same(_context));
      expect(draft.items, hasLength(2));
      expect(draft.toRequestBody(), {
        'id_sucursal': 1,
        'fecha_atencion_programada': '2026-09-14T14:00:00-04:00',
        'items': [
          {'id_variante_producto': 90, 'cantidad': 2},
          {'id_variante_producto': 92, 'cantidad': 1},
        ],
      });
    },
  );

  test('respeta stock al añadir y editar, y elimina el contexto al vaciar', () {
    final draft = ReservationDraftController();
    addTearDown(draft.dispose);
    draft.start(_context, _item(90, quantity: 2, stock: 2));

    expect(draft.add(_item(90, stock: 2)), isFalse);
    expect(draft.updateQuantity(90, 3), isFalse);
    expect(draft.items.single.quantity, 2);

    draft.remove(90);
    expect(draft.isEmpty, isTrue);
    expect(draft.context, isNull);
  });
}

const _context = ReservationContext(
  branchId: 1,
  branchName: 'Sucursal Centro',
  cityName: 'La Paz',
  address: 'Av. Principal',
  openingTime: '13:00:00',
  closingTime: '18:00:00',
  date: '2026-09-14',
  time: '14:00',
);

ReservationDraftItem _item(int variantId, {int quantity = 1, int stock = 5}) =>
    ReservationDraftItem(
      productId: variantId == 90 ? 10 : 11,
      variantId: variantId,
      productName: variantId == 90 ? 'Chaqueta' : 'Camisa',
      imageUrl: null,
      sku: 'SKU-$variantId',
      size: const CatalogSize(id: 2, name: 'M'),
      color: const CatalogColor(id: 4, name: 'Negro', hexCode: '#111111'),
      referencePrice: 80,
      quantity: quantity,
      availableStock: stock,
    );
