import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/core/theme/app_theme.dart';
import 'package:mobile/features/auth/login_models.dart';
import 'package:mobile/features/profile/profile_screen.dart';
import 'package:mobile/features/profile/profile_service.dart';

void main() {
  testWidgets('carga y muestra los datos reales disponibles del perfil', (
    tester,
  ) async {
    await _pumpProfile(tester, _FakeProfileGateway());
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('profileCard')), findsOneWidget);
    expect(find.text('Ana'), findsOneWidget);
    expect(find.text('Pérez'), findsOneWidget);
    expect(find.text('cliente@correo.com'), findsOneWidget);
    expect(find.text('CLIENTE'), findsOneWidget);
    expect(find.text('No disponible'), findsOneWidget);
    expect(find.textContaining('API de perfil actual'), findsOneWidget);
  });

  testWidgets('muestra loading mientras consulta el endpoint', (tester) async {
    final completer = Completer<AuthenticatedUser>();
    await _pumpProfile(
      tester,
      _FakeProfileGateway(handler: () => completer.future),
    );

    expect(find.byKey(const Key('profileLoadingIndicator')), findsOneWidget);
    expect(find.byKey(const Key('profileCard')), findsNothing);

    completer.complete(_client);
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('profileCard')), findsOneWidget);
  });

  testWidgets('muestra error y permite reintentar', (tester) async {
    var shouldFail = true;
    final gateway = _FakeProfileGateway(
      handler: () async {
        if (shouldFail) {
          throw const ProfileFailure(
            ProfileFailureType.connection,
            'No pudimos conectar con FashionStore. Revisa tu conexión.',
          );
        }
        return _client;
      },
    );
    await _pumpProfile(tester, gateway);
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('profileErrorContent')), findsOneWidget);
    expect(find.textContaining('Revisa tu conexión'), findsOneWidget);

    shouldFail = false;
    await tester.tap(find.byKey(const Key('retryProfileButton')));
    await tester.pumpAndSettle();
    expect(gateway.calls, 2);
    expect(find.byKey(const Key('profileCard')), findsOneWidget);
  });

  testWidgets('token inválido solicita limpiar la sesión', (tester) async {
    String? invalidSessionMessage;
    await _pumpProfile(
      tester,
      _FakeProfileGateway(
        handler: () async => throw const ProfileFailure(
          ProfileFailureType.unauthorized,
          'Tu sesión expiró. Inicia sesión nuevamente.',
        ),
      ),
      onSessionInvalidated: (message) async {
        invalidSessionMessage = message;
      },
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    expect(invalidSessionMessage, contains('sesión expiró'));
    expect(find.byKey(const Key('profileCard')), findsNothing);
  });

  testWidgets('navega a cambiar contraseña', (tester) async {
    var changePasswordCalls = 0;
    await _pumpProfile(
      tester,
      _FakeProfileGateway(),
      onChangePassword: () => changePasswordCalls++,
    );
    await tester.pumpAndSettle();

    final option = find.byKey(const Key('changePasswordOption'));
    await tester.ensureVisible(option);
    await tester.tap(option);
    expect(changePasswordCalls, 1);
  });

  testWidgets('cerrar sesión bloquea doble toque', (tester) async {
    final completer = Completer<void>();
    var logoutCalls = 0;
    await _pumpProfile(
      tester,
      _FakeProfileGateway(),
      onLogout: () {
        logoutCalls++;
        return completer.future;
      },
    );
    await tester.pumpAndSettle();

    final button = find.byKey(const Key('profileLogoutButton'));
    await tester.ensureVisible(button);
    await tester.pumpAndSettle();
    await tester.tap(button);
    await tester.tap(button);
    await tester.pump();

    expect(logoutCalls, 1);
    expect(find.text('Cerrando sesión...'), findsOneWidget);

    completer.complete();
    await tester.pumpAndSettle();
  });

  for (final size in const [Size(320, 568), Size(390, 844), Size(600, 960)]) {
    testWidgets('no produce overflow en ${size.width.toInt()} px', (
      tester,
    ) async {
      tester.view.physicalSize = size;
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await _pumpProfile(tester, _FakeProfileGateway());
      await tester.pumpAndSettle();
      await tester.drag(
        find.byKey(const Key('profileScrollView')),
        const Offset(0, -420),
      );
      await tester.pump();
      expect(tester.takeException(), isNull);
    });
  }
}

Future<void> _pumpProfile(
  WidgetTester tester,
  ProfileGateway gateway, {
  VoidCallback? onChangePassword,
  Future<void> Function()? onLogout,
  Future<void> Function(String message)? onSessionInvalidated,
}) => tester.pumpWidget(
  MaterialApp(
    theme: AppTheme.light,
    home: ProfileScreen(
      profileGateway: gateway,
      onBack: () {},
      onChangePassword: onChangePassword ?? () {},
      onLogout: onLogout ?? () async {},
      onSessionInvalidated: onSessionInvalidated,
    ),
  ),
);

const _client = AuthenticatedUser(
  userId: 42,
  firstName: 'Ana',
  lastName: 'Pérez',
  email: 'cliente@correo.com',
  role: 'CLIENTE',
);

class _FakeProfileGateway implements ProfileGateway {
  _FakeProfileGateway({this.handler});
  final Future<AuthenticatedUser> Function()? handler;
  int calls = 0;

  @override
  Future<AuthenticatedUser> loadProfile() {
    calls++;
    return handler?.call() ?? Future.value(_client);
  }
}
