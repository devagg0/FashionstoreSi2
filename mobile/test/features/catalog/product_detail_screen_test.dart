import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/core/theme/app_theme.dart';
import 'package:mobile/features/catalog/catalog_models.dart';
import 'package:mobile/features/catalog/catalog_service.dart';
import 'package:mobile/features/catalog/product_detail_screen.dart';

import 'catalog_test_data.dart';

void main() {
  testWidgets('muestra loading y error con reintento en detalle', (
    tester,
  ) async {
    final completer = Completer<CatalogProductDetail>();
    var calls = 0;
    final gateway = _DetailGateway(() {
      calls++;
      if (calls == 1) return completer.future;
      return Future.value(catalogDetail());
    });
    await _pumpDetail(tester, gateway);

    expect(find.byKey(const Key('productDetailLoading')), findsOneWidget);
    completer.completeError(
      const CatalogFailure(CatalogFailureType.server, 'Error de servidor.'),
    );
    await tester.pumpAndSettle();
    expect(find.text('Error de servidor.'), findsOneWidget);

    await tester.tap(find.byKey(const Key('retryProductDetailButton')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('productDetailName')), findsOneWidget);
    expect(calls, 2);
  });
}

Future<void> _pumpDetail(WidgetTester tester, CatalogGateway gateway) =>
    tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        home: ProductDetailScreen(productId: 10, catalogGateway: gateway),
      ),
    );

class _DetailGateway implements CatalogGateway {
  _DetailGateway(this.handler);
  final Future<CatalogProductDetail> Function() handler;
  @override
  Future<CatalogProductDetail> loadProductDetail(int productId) => handler();
  @override
  Future<CatalogPage> loadProducts(CatalogFilters filters) =>
      throw UnimplementedError();
}
