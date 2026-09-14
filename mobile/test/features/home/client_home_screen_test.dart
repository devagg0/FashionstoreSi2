import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/core/theme/app_theme.dart';
import 'package:mobile/features/auth/login_models.dart';
import 'package:mobile/features/home/client_home_screen.dart';

void main() {
  testWidgets('saluda al cliente y ejecuta logout una sola vez', (
    tester,
  ) async {
    final completer = Completer<void>();
    var logoutCalls = 0;
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        home: ClientHomeScreen(
          user: _client,
          onOpenProfile: () {},
          onOpenCatalog: () {},
          onOpenReservations: () {},
          onLogout: () {
            logoutCalls++;
            return completer.future;
          },
        ),
      ),
    );

    expect(find.text('Hola, Ana'), findsOneWidget);
    expect(find.text('Ana Pérez'), findsOneWidget);
    expect(find.text('cliente@correo.com'), findsOneWidget);

    final logout = find.byKey(const Key('logoutButton'));
    await tester.tap(logout);
    await tester.tap(logout);
    await tester.pump();

    expect(logoutCalls, 1);
    expect(find.byKey(const Key('logoutLoading')), findsOneWidget);

    completer.complete();
    await tester.pumpAndSettle();
  });

  testWidgets('abre Mi perfil desde el inicio', (tester) async {
    var profileCalls = 0;
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        home: ClientHomeScreen(
          user: _client,
          onOpenProfile: () => profileCalls++,
          onOpenCatalog: () {},
          onOpenReservations: () {},
          onLogout: () async {},
        ),
      ),
    );

    await tester.tap(find.byKey(const Key('openProfileButton')));
    expect(profileCalls, 1);
  });

  testWidgets('abre el catálogo desde el inicio', (tester) async {
    var catalogCalls = 0;
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        home: ClientHomeScreen(
          user: _client,
          onOpenProfile: () {},
          onOpenCatalog: () => catalogCalls++,
          onOpenReservations: () {},
          onLogout: () async {},
        ),
      ),
    );

    await tester.tap(find.byKey(const Key('openCatalogButton')));
    expect(catalogCalls, 1);
  });

  testWidgets('abre Mis reservas desde el inicio', (tester) async {
    var calls = 0;
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        home: ClientHomeScreen(
          user: _client,
          onOpenProfile: () {},
          onOpenCatalog: () {},
          onOpenReservations: () => calls++,
          onLogout: () async {},
        ),
      ),
    );

    await tester.tap(find.byKey(const Key('openReservationsButton')));
    expect(calls, 1);
  });
}

const _client = AuthenticatedUser(
  userId: 42,
  firstName: 'Ana',
  lastName: 'Pérez',
  email: 'cliente@correo.com',
  role: 'CLIENTE',
);
