import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/core/theme/app_theme.dart';
import 'package:mobile/features/catalog/availability_models.dart';
import 'package:mobile/features/catalog/catalog_models.dart';
import 'package:mobile/features/reservations/reservation_draft.dart';
import 'package:mobile/features/reservations/widgets/reservation_action_panel.dart';

import '../catalog/catalog_test_data.dart';

void main() {
  testWidgets('primera prenda solicita sucursal, día y horario', (
    tester,
  ) async {
    final draft = ReservationDraftController();
    addTearDown(draft.dispose);
    await _pump(tester, draft, _selection(_variant90));

    await tester.tap(find.byKey(const Key('reservationBranchField')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Sucursal Centro · La Paz').last);
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('reservationDay-2026-09-13')), findsOneWidget);
    final time = find.byKey(const Key('reservationTime-13:00'));
    await tester.ensureVisible(time);
    await tester.pumpAndSettle();
    await tester.tap(time);
    await tester.tap(find.byKey(const Key('increaseReservationQuantity')));
    final start = find.byKey(const Key('startReservationButton'));
    await tester.ensureVisible(start);
    await tester.pumpAndSettle();
    await tester.tap(start);
    await tester.pump();

    expect(draft.context?.branchId, 1);
    expect(draft.context?.date, '2026-09-13');
    expect(draft.context?.time, '13:00');
    expect(draft.items.single.quantity, 2);
  });

  testWidgets('segunda prenda conserva contexto y solo solicita cantidad', (
    tester,
  ) async {
    final draft = ReservationDraftController();
    addTearDown(draft.dispose);
    draft.start(_context, _draftItem(_variant90));

    await _pump(tester, draft, _selection(_variant92));

    expect(find.byKey(const Key('fixedReservationContext')), findsOneWidget);
    expect(find.byKey(const Key('reservationBranchField')), findsNothing);
    expect(find.byKey(const Key('reservationDay-2026-09-13')), findsNothing);
    await tester.tap(find.byKey(const Key('addToReservationButton')));
    await tester.pump();
    expect(draft.items.map((item) => item.variantId), [90, 92]);
    expect(draft.context, same(_context));
  });

  testWidgets('bloquea la segunda prenda sin stock en la sucursal fijada', (
    tester,
  ) async {
    final draft = ReservationDraftController();
    addTearDown(draft.dispose);
    draft.start(_context, _draftItem(_variant90));
    await _pump(
      tester,
      draft,
      VariantAvailabilitySelection(
        variant: _variant92,
        branches: [_branch(variant: _variant92, stock: 0)],
      ),
    );

    expect(find.byKey(const Key('reservationNoStock')), findsOneWidget);
    expect(find.byKey(const Key('addToReservationButton')), findsNothing);
  });
}

Future<void> _pump(
  WidgetTester tester,
  ReservationDraftController draft,
  VariantAvailabilitySelection selection,
) => tester.pumpWidget(
  MaterialApp(
    theme: AppTheme.light,
    home: Scaffold(
      body: SingleChildScrollView(
        child: ReservationActionPanel(
          product: catalogDetail(),
          selection: selection,
          draft: draft,
          onOpenDraft: () {},
          now: DateTime.utc(2026, 9, 13, 16),
        ),
      ),
    ),
  ),
);

VariantAvailabilitySelection _selection(CatalogVariant variant) =>
    VariantAvailabilitySelection(
      variant: variant,
      branches: [_branch(variant: variant, stock: 5)],
    );

BranchAvailability _branch({
  required CatalogVariant variant,
  required int stock,
}) => BranchAvailability(
  variantId: variant.id,
  sku: variant.sku,
  size: variant.size,
  color: variant.color,
  branchId: 1,
  branchName: 'Sucursal Centro',
  cityId: 2,
  cityName: 'La Paz',
  address: 'Av. Principal 100',
  openingTime: '13:00:00',
  closingTime: '18:00:00',
  availableStock: stock,
);

ReservationDraftItem _draftItem(CatalogVariant variant) => ReservationDraftItem(
  productId: 10,
  variantId: variant.id,
  productName: 'Chaqueta urbana',
  imageUrl: null,
  sku: variant.sku,
  size: variant.size,
  color: variant.color,
  referencePrice: 80,
  quantity: 1,
  availableStock: 5,
);

const _context = ReservationContext(
  branchId: 1,
  branchName: 'Sucursal Centro',
  cityName: 'La Paz',
  address: 'Av. Principal 100',
  openingTime: '13:00:00',
  closingTime: '18:00:00',
  date: '2026-09-13',
  time: '13:00',
);

const _variant90 = CatalogVariant(
  id: 90,
  sku: 'CHA-NEG-M',
  size: CatalogSize(id: 2, name: 'M'),
  color: CatalogColor(id: 4, name: 'Negro', hexCode: '#111111'),
  branchAvailability: null,
);
const _variant92 = CatalogVariant(
  id: 92,
  sku: 'CHA-ROJ-M',
  size: CatalogSize(id: 2, name: 'M'),
  color: CatalogColor(id: 5, name: 'Rojo', hexCode: '#AA1111'),
  branchAvailability: null,
);
