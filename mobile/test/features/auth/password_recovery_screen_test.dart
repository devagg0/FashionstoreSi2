import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/core/theme/app_theme.dart';
import 'package:mobile/features/auth/password_recovery_models.dart';
import 'package:mobile/features/auth/password_recovery_screen.dart';
import 'package:mobile/features/auth/password_recovery_service.dart';

void main() {
  testWidgets('completa solicitud, código, nueva contraseña y regreso', (
    tester,
  ) async {
    final gateway = _FakeRecoveryGateway();
    var backToLoginCalls = 0;
    await _pumpScreen(tester, gateway, onBackToLogin: () => backToLoginCalls++);

    expect(find.text('¿Olvidaste tu contraseña?'), findsOneWidget);
    await tester.enterText(
      find.byKey(const Key('recoveryEmailField')),
      '  CLIENTE@CORREO.COM ',
    );
    await _tapVisible(tester, const Key('requestRecoveryButton'));

    expect(find.byKey(const Key('recoveryCodeStep')), findsOneWidget);
    expect(find.byKey(const Key('passwordRecoveryInfo')), findsOneWidget);
    expect(gateway.lastEmail, 'cliente@correo.com');

    await tester.enterText(
      find.byKey(const Key('recoveryCodeField')),
      '123456',
    );
    await _tapVisible(tester, const Key('verifyRecoveryCodeButton'));

    expect(find.byKey(const Key('recoveryPasswordStep')), findsOneWidget);
    expect(gateway.lastCode, '123456');

    await tester.enterText(
      find.byKey(const Key('recoveryPasswordField')),
      'Nueva@2026',
    );
    await tester.enterText(
      find.byKey(const Key('recoveryConfirmationField')),
      'Nueva@2026',
    );
    await _tapVisible(tester, const Key('resetPasswordButton'));

    expect(find.byKey(const Key('passwordRecoverySuccess')), findsOneWidget);
    expect(find.text('Contraseña actualizada'), findsOneWidget);
    expect(gateway.lastResetToken, 'reset.jwt');
    expect(gateway.lastPassword, 'Nueva@2026');
    expect(gateway.requestCalls, 1);
    expect(gateway.verifyCalls, 1);
    expect(gateway.resetCalls, 1);

    await _tapVisible(tester, const Key('recoveryBackToLoginButton'));
    expect(backToLoginCalls, 1);
  });

  testWidgets('valida localmente correo, código y contraseñas', (tester) async {
    final gateway = _FakeRecoveryGateway();
    await _pumpScreen(tester, gateway);

    await _tapVisible(tester, const Key('requestRecoveryButton'));
    expect(find.text('El correo electrónico es obligatorio.'), findsOneWidget);
    expect(gateway.requestCalls, 0);

    await tester.enterText(
      find.byKey(const Key('recoveryEmailField')),
      'cliente@correo.com',
    );
    await _tapVisible(tester, const Key('requestRecoveryButton'));
    await tester.enterText(find.byKey(const Key('recoveryCodeField')), '12345');
    await _tapVisible(tester, const Key('verifyRecoveryCodeButton'));
    expect(
      find.text('Ingresa el código numérico de 6 dígitos.'),
      findsOneWidget,
    );
    expect(gateway.verifyCalls, 0);

    await tester.enterText(
      find.byKey(const Key('recoveryCodeField')),
      '123456',
    );
    await _tapVisible(tester, const Key('verifyRecoveryCodeButton'));
    await tester.enterText(
      find.byKey(const Key('recoveryPasswordField')),
      'Nueva@2026',
    );
    await tester.enterText(
      find.byKey(const Key('recoveryConfirmationField')),
      'Distinta@2026',
    );
    await _tapVisible(tester, const Key('resetPasswordButton'));
    expect(find.text('Las contraseñas no coinciden.'), findsOneWidget);
    expect(gateway.resetCalls, 0);
  });

  testWidgets('loading bloquea doble solicitud', (tester) async {
    final completer = Completer<String>();
    final gateway = _FakeRecoveryGateway(
      requestHandler: (_) => completer.future,
    );
    await _pumpScreen(tester, gateway);
    await tester.enterText(
      find.byKey(const Key('recoveryEmailField')),
      'cliente@correo.com',
    );
    final button = find.byKey(const Key('requestRecoveryButton'));
    await tester.ensureVisible(button);
    await tester.tap(button);
    await tester.tap(button);
    await tester.pump();

    expect(gateway.requestCalls, 1);
    expect(find.byKey(const Key('passwordRecoveryLoading')), findsOneWidget);
    expect(tester.widget<FilledButton>(button).onPressed, isNull);

    completer.complete(_requestMessage);
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('recoveryCodeStep')), findsOneWidget);
  });

  testWidgets('muestra conexión fallida y permite reintentar', (tester) async {
    final gateway = _FakeRecoveryGateway(
      requestHandler: (_) async => throw const PasswordRecoveryFailure(
        PasswordRecoveryFailureType.connection,
        'No pudimos conectar con FashionStore. Revisa tu conexión.',
      ),
    );
    await _pumpScreen(tester, gateway);
    await tester.enterText(
      find.byKey(const Key('recoveryEmailField')),
      'cliente@correo.com',
    );
    await _tapVisible(tester, const Key('requestRecoveryButton'));

    expect(find.byKey(const Key('passwordRecoveryError')), findsOneWidget);
    expect(find.textContaining('Revisa tu conexión'), findsOneWidget);
    expect(
      tester
          .widget<FilledButton>(find.byKey(const Key('requestRecoveryButton')))
          .onPressed,
      isNotNull,
    );
  });

  testWidgets('mantiene el paso de código ante código inválido o expirado', (
    tester,
  ) async {
    final gateway = _FakeRecoveryGateway(
      verifyHandler: (_) async => throw const PasswordRecoveryFailure(
        PasswordRecoveryFailureType.invalidCode,
        'El código es inválido o expiró. Solicita uno nuevo si es necesario.',
      ),
    );
    await _pumpScreen(tester, gateway);
    await tester.enterText(
      find.byKey(const Key('recoveryEmailField')),
      'cliente@correo.com',
    );
    await _tapVisible(tester, const Key('requestRecoveryButton'));
    await tester.enterText(
      find.byKey(const Key('recoveryCodeField')),
      '000000',
    );
    await _tapVisible(tester, const Key('verifyRecoveryCodeButton'));

    expect(find.byKey(const Key('recoveryCodeStep')), findsOneWidget);
    expect(find.textContaining('inválido o expiró'), findsOneWidget);
    expect(find.byKey(const Key('resendRecoveryCodeButton')), findsOneWidget);
  });

  testWidgets('ofrece reiniciar cuando el reset token expiró', (tester) async {
    final gateway = _FakeRecoveryGateway(
      resetHandler: (_) async => throw const PasswordRecoveryFailure(
        PasswordRecoveryFailureType.invalidResetToken,
        'La autorización para cambiar la contraseña es inválida o expiró.',
      ),
    );
    await _pumpScreen(tester, gateway);
    await tester.enterText(
      find.byKey(const Key('recoveryEmailField')),
      'cliente@correo.com',
    );
    await _tapVisible(tester, const Key('requestRecoveryButton'));
    await tester.enterText(
      find.byKey(const Key('recoveryCodeField')),
      '123456',
    );
    await _tapVisible(tester, const Key('verifyRecoveryCodeButton'));
    await tester.enterText(
      find.byKey(const Key('recoveryPasswordField')),
      'Nueva@2026',
    );
    await tester.enterText(
      find.byKey(const Key('recoveryConfirmationField')),
      'Nueva@2026',
    );
    await _tapVisible(tester, const Key('resetPasswordButton'));

    expect(find.textContaining('inválida o expiró'), findsOneWidget);
    expect(find.byKey(const Key('restartRecoveryButton')), findsOneWidget);
  });

  for (final size in const [Size(320, 568), Size(390, 844), Size(600, 960)]) {
    testWidgets('no produce overflow en ${size.width.toInt()} px', (
      tester,
    ) async {
      tester.view.physicalSize = size;
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await _pumpScreen(tester, _FakeRecoveryGateway());
      await tester.drag(
        find.byKey(const Key('passwordRecoveryScrollView')),
        const Offset(0, -350),
      );
      await tester.pump();
      expect(tester.takeException(), isNull);
    });
  }
}

Future<void> _pumpScreen(
  WidgetTester tester,
  PasswordRecoveryGateway gateway, {
  VoidCallback? onBackToLogin,
}) => tester.pumpWidget(
  MaterialApp(
    theme: AppTheme.light,
    home: PasswordRecoveryScreen(
      recoveryGateway: gateway,
      onBackToLogin: onBackToLogin,
    ),
  ),
);

Future<void> _tapVisible(WidgetTester tester, Key key) async {
  final finder = find.byKey(key);
  await tester.ensureVisible(finder);
  await tester.pumpAndSettle();
  await tester.tap(finder);
  await tester.pumpAndSettle();
}

const _requestMessage =
    'Si el correo está registrado, recibirás un código de recuperación';

class _FakeRecoveryGateway implements PasswordRecoveryGateway {
  _FakeRecoveryGateway({
    this.requestHandler,
    this.verifyHandler,
    this.resetHandler,
  });

  final Future<String> Function(PasswordRecoveryRequest request)?
  requestHandler;
  final Future<PasswordRecoveryVerificationResult> Function(
    PasswordRecoveryVerificationRequest request,
  )?
  verifyHandler;
  final Future<String> Function(PasswordResetRequest request)? resetHandler;

  int requestCalls = 0;
  int verifyCalls = 0;
  int resetCalls = 0;
  String? lastEmail;
  String? lastCode;
  String? lastResetToken;
  String? lastPassword;

  @override
  Future<String> requestRecovery(PasswordRecoveryRequest request) {
    requestCalls++;
    lastEmail = request.email;
    return requestHandler?.call(request) ?? Future.value(_requestMessage);
  }

  @override
  Future<String> resetPassword(PasswordResetRequest request) {
    resetCalls++;
    lastResetToken = request.resetToken;
    lastPassword = request.newPassword;
    return resetHandler?.call(request) ??
        Future.value('Contraseña restablecida correctamente');
  }

  @override
  Future<PasswordRecoveryVerificationResult> verifyCode(
    PasswordRecoveryVerificationRequest request,
  ) {
    verifyCalls++;
    lastEmail = request.email;
    lastCode = request.code;
    return verifyHandler?.call(request) ??
        Future.value(
          const PasswordRecoveryVerificationResult(
            message: 'Código verificado correctamente',
            resetToken: 'reset.jwt',
          ),
        );
  }
}
