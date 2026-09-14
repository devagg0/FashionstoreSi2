import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/core/theme/app_theme.dart';
import 'package:mobile/features/catalog/availability_models.dart';
import 'package:mobile/features/catalog/availability_service.dart';
import 'package:mobile/features/catalog/catalog_models.dart';
import 'package:mobile/features/catalog/widgets/product_availability_panel.dart';

void main() {
  testWidgets('consulta la variante elegida y muestra varias sucursales', (
    tester,
  ) async {
    final completer = Completer<CatalogAvailabilityResult>();
    final gateway = _FakeAvailabilityGateway((_, _) => completer.future);
    await _pumpPanel(tester, gateway);

    await _choose(tester, sizeId: 2, colorId: 4, settle: false);
    expect(find.byKey(const Key('availabilityLoading')), findsOneWidget);
    expect(gateway.variantIds, [90]);

    completer.complete(_result(_branches));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('availabilityBranchList')), findsOneWidget);
    expect(find.text('Sucursal Centro'), findsOneWidget);
    expect(find.text('La Paz'), findsOneWidget);
    expect(find.text('Negro · Talla M'), findsNWidgets(2));
    expect(find.text('SKU CHA-NEG-M'), findsNWidgets(2));
    expect(find.text('Stock: 6'), findsOneWidget);
    expect(find.text('Sin disponibilidad'), findsOneWidget);
    expect(find.textContaining('stock_actual'), findsNothing);
    expect(find.textContaining('stock_reservado'), findsNothing);
  });

  testWidgets('actualiza automáticamente al cambiar talla y color', (
    tester,
  ) async {
    final gateway = _FakeAvailabilityGateway(
      (_, variantId) async =>
          _result([_branch(variantId: variantId, stock: variantId)]),
    );
    await _pumpPanel(tester, gateway);

    await _choose(tester, sizeId: 2, colorId: 4);
    await tester.tap(find.byKey(const Key('availabilitySize-3')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('availabilitySize-2')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('availabilityColor-5')));
    await tester.pumpAndSettle();

    expect(gateway.variantIds, [90, 91, 90, 92]);
    expect(find.text('Rojo · Talla M'), findsOneWidget);
    expect(find.text('SKU CHA-ROJ-M'), findsOneWidget);
  });

  testWidgets('muestra Sin disponibilidad para respuesta vacía', (
    tester,
  ) async {
    final gateway = _FakeAvailabilityGateway((_, _) async => _result(const []));
    await _pumpPanel(tester, gateway);
    await _choose(tester, sizeId: 2, colorId: 4);

    expect(find.byKey(const Key('availabilityEmpty')), findsOneWidget);
    expect(find.text('Sin disponibilidad'), findsOneWidget);
  });

  testWidgets('muestra error de conexión y permite reintentar', (tester) async {
    var fail = true;
    final gateway = _FakeAvailabilityGateway((_, _) async {
      if (fail) {
        throw const AvailabilityFailure(
          AvailabilityFailureType.connection,
          'No pudimos consultar la disponibilidad. Revisa tu conexión.',
        );
      }
      return _result(_branches);
    });
    await _pumpPanel(tester, gateway);
    await _choose(tester, sizeId: 2, colorId: 4);

    expect(find.textContaining('Revisa tu conexión'), findsOneWidget);
    fail = false;
    await tester.tap(find.byKey(const Key('retryAvailabilityButton')));
    await tester.pumpAndSettle();
    expect(find.text('Sucursal Centro'), findsOneWidget);
    expect(gateway.variantIds, [90, 90]);
  });

  testWidgets('no produce overflow con varias sucursales en 320 px', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(320, 700);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final gateway = _FakeAvailabilityGateway(
      (_, _) async => _result(_branches),
    );
    await _pumpPanel(tester, gateway);
    await _choose(tester, sizeId: 2, colorId: 4);
    expect(tester.takeException(), isNull);
  });
}

Future<void> _pumpPanel(
  WidgetTester tester,
  CatalogAvailabilityGateway gateway,
) => tester.pumpWidget(
  MaterialApp(
    theme: AppTheme.light,
    home: Scaffold(
      body: SingleChildScrollView(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: ProductAvailabilityPanel(
            productId: 10,
            variants: _variants,
            sizes: _sizes,
            colors: _colors,
            availabilityGateway: gateway,
          ),
        ),
      ),
    ),
  ),
);

Future<void> _choose(
  WidgetTester tester, {
  required int sizeId,
  required int colorId,
  bool settle = true,
}) async {
  await tester.tap(find.byKey(Key('availabilitySize-$sizeId')));
  await tester.tap(find.byKey(Key('availabilityColor-$colorId')));
  await tester.pump();
  if (settle) {
    await tester.pumpAndSettle();
  }
}

class _FakeAvailabilityGateway implements CatalogAvailabilityGateway {
  _FakeAvailabilityGateway(this.handler);
  final Future<CatalogAvailabilityResult> Function(int productId, int variantId)
  handler;
  final List<int> variantIds = [];

  @override
  Future<CatalogAvailabilityResult> loadVariantAvailability({
    required int productId,
    required int variantId,
  }) {
    variantIds.add(variantId);
    return handler(productId, variantId);
  }
}

CatalogAvailabilityResult _result(List<BranchAvailability> branches) =>
    CatalogAvailabilityResult(
      productId: 10,
      productName: 'Chaqueta urbana',
      branches: branches,
    );

BranchAvailability _branch({
  int variantId = 90,
  int stock = 6,
  int branchId = 1,
}) {
  final variant = _variants.firstWhere((item) => item.id == variantId);
  return BranchAvailability(
    variantId: variantId,
    sku: variant.sku,
    size: variant.size,
    color: variant.color,
    branchId: branchId,
    branchName: branchId == 1 ? 'Sucursal Centro' : 'Sucursal Norte',
    cityId: branchId == 1 ? 2 : 4,
    cityName: branchId == 1 ? 'La Paz' : 'El Alto',
    address: 'Av. Principal 100',
    openingTime: '09:00:00',
    closingTime: '18:00:00',
    availableStock: stock,
  );
}

final _branches = [_branch(), _branch(stock: 0, branchId: 3)];

const _sizes = [CatalogSize(id: 2, name: 'M'), CatalogSize(id: 3, name: 'L')];
const _colors = [
  CatalogColor(id: 4, name: 'Negro', hexCode: '#111111'),
  CatalogColor(id: 5, name: 'Rojo', hexCode: '#AA1111'),
];
const _variants = [
  CatalogVariant(
    id: 90,
    sku: 'CHA-NEG-M',
    size: CatalogSize(id: 2, name: 'M'),
    color: CatalogColor(id: 4, name: 'Negro', hexCode: '#111111'),
    branchAvailability: null,
  ),
  CatalogVariant(
    id: 91,
    sku: 'CHA-NEG-L',
    size: CatalogSize(id: 3, name: 'L'),
    color: CatalogColor(id: 4, name: 'Negro', hexCode: '#111111'),
    branchAvailability: null,
  ),
  CatalogVariant(
    id: 92,
    sku: 'CHA-ROJ-M',
    size: CatalogSize(id: 2, name: 'M'),
    color: CatalogColor(id: 5, name: 'Rojo', hexCode: '#AA1111'),
    branchAvailability: null,
  ),
];
