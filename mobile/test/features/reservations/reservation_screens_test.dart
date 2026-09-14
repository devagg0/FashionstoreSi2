import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/core/theme/app_theme.dart';
import 'package:mobile/features/catalog/catalog_models.dart';
import 'package:mobile/features/reservations/my_reservations_screen.dart';
import 'package:mobile/features/reservations/reservation_detail_screen.dart';
import 'package:mobile/features/reservations/reservation_draft.dart';
import 'package:mobile/features/reservations/reservation_draft_screen.dart';
import 'package:mobile/features/reservations/reservation_models.dart';
import 'package:mobile/features/reservations/reservation_service.dart';

import 'reservation_test_data.dart';

void main() {
  testWidgets('confirma la reserva temporal completa con un solo POST', (
    tester,
  ) async {
    final draft = _populatedDraft();
    addTearDown(draft.dispose);
    final completer = Completer<ReservationDetail>();
    final gateway = _FakeReservationGateway(
      createHandler: (_) => completer.future,
    );
    ReservationDetail? created;
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        home: ReservationDraftScreen(
          draft: draft,
          reservationGateway: gateway,
          onBack: () {},
          onContinueShopping: () {},
          onCreated: (value) => created = value,
          onSessionInvalidated: (_) async {},
        ),
      ),
    );

    final confirm = find.byKey(const Key('confirmReservationButton'));
    await tester.ensureVisible(confirm);
    await tester.pumpAndSettle();
    await tester.tap(confirm);
    await tester.tap(confirm);
    await tester.pump();

    expect(gateway.createRequests, hasLength(1));
    expect(gateway.createRequests.single['items'], hasLength(2));
    expect(find.byKey(const Key('confirmReservationLoading')), findsOneWidget);
    completer.complete(reservationDetail());
    await tester.pumpAndSettle();
    expect(created?.id, 9);
    expect(draft.isEmpty, isTrue);
  });

  testWidgets('lista reservas reales y abre su detalle', (tester) async {
    final gateway = _FakeReservationGateway();
    int? selected;
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        home: MyReservationsScreen(
          reservationGateway: gateway,
          onBack: () {},
          onOpenDetail: (id) => selected = id,
          onSessionInvalidated: (_) async {},
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('RSV-20260913-ABC123'), findsOneWidget);
    expect(find.text('Pendiente'), findsOneWidget);
    expect(find.text('Sucursal Centro · La Paz'), findsOneWidget);
    expect(find.text('3 prendas'), findsOneWidget);
    expect(find.text('Bs 260.00'), findsOneWidget);
    await tester.tap(find.byKey(const Key('reservation-9')));
    expect(selected, 9);
  });

  testWidgets('muestra detalle y cancela cuando backend lo permite', (
    tester,
  ) async {
    final gateway = _FakeReservationGateway();
    await _pumpDetail(tester, gateway, reservationDetail());

    expect(find.text('Chaqueta urbana'), findsOneWidget);
    final cancel = find.byKey(const Key('cancelReservationButton'));
    await tester.ensureVisible(cancel);
    await tester.pumpAndSettle();
    await tester.tap(cancel);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('confirmCancelReservationButton')));
    await tester.pumpAndSettle();

    expect(gateway.cancelIds, [9]);
    expect(find.text('Cancelada'), findsOneWidget);
    expect(find.byKey(const Key('cancelReservationButton')), findsNothing);
  });

  for (final state in const [
    ReservationState.atendida,
    ReservationState.cancelada,
    ReservationState.expirada,
  ]) {
    testWidgets('${state.apiValue} bloquea cancelación', (tester) async {
      await _pumpDetail(
        tester,
        _FakeReservationGateway(),
        reservationDetail(state: state, cancelable: false),
      );
      expect(find.text(state.label), findsOneWidget);
      expect(find.byKey(const Key('cancelReservationButton')), findsNothing);
    });
  }

  testWidgets('reserva temporal, listado y detalle no desbordan en 320 px', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(320, 700);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final gateway = _FakeReservationGateway();
    final draft = _populatedDraft();
    addTearDown(draft.dispose);

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        home: ReservationDraftScreen(
          draft: draft,
          reservationGateway: gateway,
          onBack: () {},
          onContinueShopping: () {},
          onCreated: (_) {},
          onSessionInvalidated: (_) async {},
        ),
      ),
    );
    await tester.pumpAndSettle();
    final draftException = tester.takeException();
    expect(draftException, isNull);

    await _pumpDetail(tester, gateway, reservationDetail());
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        home: MyReservationsScreen(
          reservationGateway: gateway,
          onBack: () {},
          onOpenDetail: (_) {},
          onSessionInvalidated: (_) async {},
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });
}

Future<void> _pumpDetail(
  WidgetTester tester,
  ReservationGateway gateway,
  ReservationDetail reservation,
) => tester.pumpWidget(
  MaterialApp(
    theme: AppTheme.light,
    home: ReservationDetailScreen(
      reservationId: reservation.id,
      initialReservation: reservation,
      reservationGateway: gateway,
      onBack: () {},
      onSessionInvalidated: (_) async {},
    ),
  ),
);

ReservationDraftController _populatedDraft() {
  final draft = ReservationDraftController();
  draft.start(_context, _draftItem(90, 10, 'Chaqueta'));
  draft.add(_draftItem(92, 11, 'Camisa'));
  return draft;
}

const _context = ReservationContext(
  branchId: 1,
  branchName: 'Sucursal Centro',
  cityName: 'La Paz',
  address: 'Av. Principal',
  openingTime: '09:00:00',
  closingTime: '18:00:00',
  date: '2026-09-14',
  time: '14:00',
);

ReservationDraftItem _draftItem(int variantId, int productId, String name) =>
    ReservationDraftItem(
      productId: productId,
      variantId: variantId,
      productName: name,
      imageUrl: null,
      sku: 'SKU-$variantId',
      size: const CatalogSize(id: 2, name: 'M'),
      color: const CatalogColor(id: 4, name: 'Negro', hexCode: '#111111'),
      referencePrice: 80,
      quantity: 1,
      availableStock: 5,
    );

class _FakeReservationGateway implements ReservationGateway {
  _FakeReservationGateway({this.createHandler});
  final Future<ReservationDetail> Function(Map<String, dynamic>)? createHandler;
  final List<Map<String, dynamic>> createRequests = [];
  final List<int> cancelIds = [];

  @override
  Future<ReservationDetail> create(Map<String, dynamic> request) {
    createRequests.add(request);
    return createHandler?.call(request) ?? Future.value(reservationDetail());
  }

  @override
  Future<ReservationPage> list({
    ReservationState? state,
    int page = 1,
    int pageSize = 10,
  }) async => ReservationPage(
    data: [reservationDetail()],
    pagination: const ReservationPagination(
      page: 1,
      pageSize: 10,
      total: 1,
      totalPages: 1,
    ),
  );

  @override
  Future<ReservationDetail> getDetail(int reservationId) async =>
      reservationDetail();

  @override
  Future<ReservationDetail> cancel(int reservationId) async {
    cancelIds.add(reservationId);
    return reservationDetail(
      state: ReservationState.cancelada,
      cancelable: false,
    );
  }
}
