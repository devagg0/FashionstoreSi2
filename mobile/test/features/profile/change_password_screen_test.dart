import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/core/theme/app_theme.dart';
import 'package:mobile/features/profile/change_password_models.dart';
import 'package:mobile/features/profile/change_password_screen.dart';
import 'package:mobile/features/profile/change_password_service.dart';

void main() {
  testWidgets('valida los tres campos antes de enviar', (tester) async {
    final gateway = _FakeChangePasswordGateway();
    await _pumpScreen(tester, gateway);

    await _tapVisible(tester, const Key('changePasswordSubmitButton'));

    expect(find.text('La contraseña actual es obligatoria.'), findsOneWidget);
    expect(find.text('La contraseña es obligatoria.'), findsOneWidget);
    expect(find.text('Confirma tu contraseña.'), findsOneWidget);
    expect(gateway.calls, 0);
  });

  testWidgets('bloquea doble envío, muestra éxito y vuelve a Mi perfil', (
    tester,
  ) async {
    final completer = Completer<String>();
    final gateway = _FakeChangePasswordGateway(
      handler: (_) => completer.future,
    );
    var backCalls = 0;
    await _pumpScreen(tester, gateway, onBackToProfile: () => backCalls++);
    await _fillValidForm(tester);

    final button = find.byKey(const Key('changePasswordSubmitButton'));
    await tester.ensureVisible(button);
    await tester.pumpAndSettle();
    await tester.tap(button);
    await tester.tap(button);
    await tester.pump();

    expect(gateway.calls, 1);
    expect(gateway.lastRequest?.currentPassword, 'Actual@2026');
    expect(gateway.lastRequest?.newPassword, 'Nueva@2026');
    expect(gateway.lastRequest?.confirmPassword, 'Nueva@2026');
    expect(find.byKey(const Key('changePasswordLoading')), findsOneWidget);
    expect(tester.widget<FilledButton>(button).onPressed, isNull);

    completer.complete('Contraseña actualizada correctamente');
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('changePasswordSuccess')), findsOneWidget);
    expect(find.text('Contraseña actualizada'), findsOneWidget);
    await _tapVisible(tester, const Key('changePasswordBackToProfileButton'));
    expect(backCalls, 1);
  });

  testWidgets('muestra contraseña actual incorrecta junto al campo', (
    tester,
  ) async {
    final gateway = _FakeChangePasswordGateway(
      handler: (_) async => throw const ChangePasswordFailure(
        ChangePasswordFailureType.incorrectCurrentPassword,
        'La contraseña actual es incorrecta.',
      ),
    );
    await _pumpScreen(tester, gateway);
    await _fillValidForm(tester);
    await _tapVisible(tester, const Key('changePasswordSubmitButton'));

    expect(find.byKey(const Key('changePasswordError')), findsOneWidget);
    expect(find.text('La contraseña actual es incorrecta.'), findsWidgets);
  });

  testWidgets('sesión expirada activa cierre de sesión y no muestra éxito', (
    tester,
  ) async {
    final gateway = _FakeChangePasswordGateway(
      handler: (_) async => throw const ChangePasswordFailure(
        ChangePasswordFailureType.unauthorized,
        'Tu sesión expiró. Inicia sesión nuevamente.',
      ),
    );
    var invalidSessionCalls = 0;
    String? invalidSessionMessage;
    await _pumpScreen(
      tester,
      gateway,
      onSessionInvalidated: (message) async {
        invalidSessionCalls++;
        invalidSessionMessage = message;
      },
    );
    await _fillValidForm(tester);
    await _tapVisible(tester, const Key('changePasswordSubmitButton'));

    expect(invalidSessionCalls, 1);
    expect(invalidSessionMessage, contains('sesión expiró'));
    expect(find.byKey(const Key('changePasswordSuccess')), findsNothing);
  });

  testWidgets('permite mostrar y ocultar las contraseñas', (tester) async {
    await _pumpScreen(tester, _FakeChangePasswordGateway());
    final currentField = find.byKey(const Key('currentPasswordField'));
    final editable = find.descendant(
      of: currentField,
      matching: find.byType(EditableText),
    );

    expect(tester.widget<EditableText>(editable).obscureText, isTrue);
    await tester.tap(find.byTooltip('Mostrar contraseña actual'));
    await tester.pump();
    expect(tester.widget<EditableText>(editable).obscureText, isFalse);
  });

  for (final size in const [Size(320, 568), Size(390, 844), Size(600, 960)]) {
    testWidgets('no produce overflow en ${size.width.toInt()} px', (
      tester,
    ) async {
      tester.view.physicalSize = size;
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await _pumpScreen(tester, _FakeChangePasswordGateway());
      await tester.drag(
        find.byKey(const Key('changePasswordScrollView')),
        const Offset(0, -500),
      );
      await tester.pump();
      expect(tester.takeException(), isNull);
    });
  }
}

Future<void> _pumpScreen(
  WidgetTester tester,
  ChangePasswordGateway gateway, {
  VoidCallback? onBackToProfile,
  Future<void> Function(String message)? onSessionInvalidated,
}) => tester.pumpWidget(
  MaterialApp(
    theme: AppTheme.light,
    home: ChangePasswordScreen(
      changePasswordGateway: gateway,
      onBackToProfile: onBackToProfile ?? () {},
      onSessionInvalidated: onSessionInvalidated,
    ),
  ),
);

Future<void> _fillValidForm(WidgetTester tester) async {
  await tester.enterText(
    find.byKey(const Key('currentPasswordField')),
    'Actual@2026',
  );
  await tester.enterText(
    find.byKey(const Key('newPasswordField')),
    'Nueva@2026',
  );
  await tester.enterText(
    find.byKey(const Key('newPasswordConfirmationField')),
    'Nueva@2026',
  );
  await tester.pump();
}

Future<void> _tapVisible(WidgetTester tester, Key key) async {
  final finder = find.byKey(key);
  await tester.ensureVisible(finder);
  await tester.pumpAndSettle();
  await tester.tap(finder);
  await tester.pumpAndSettle();
}

class _FakeChangePasswordGateway implements ChangePasswordGateway {
  _FakeChangePasswordGateway({this.handler});

  final Future<String> Function(ChangePasswordRequest request)? handler;
  int calls = 0;
  ChangePasswordRequest? lastRequest;

  @override
  Future<String> changePassword(ChangePasswordRequest request) {
    calls++;
    lastRequest = request;
    return handler?.call(request) ??
        Future.value('Contraseña actualizada correctamente');
  }
}
