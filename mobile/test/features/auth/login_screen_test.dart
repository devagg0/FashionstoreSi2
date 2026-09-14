import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/core/theme/app_theme.dart';
import 'package:mobile/features/auth/login_models.dart';
import 'package:mobile/features/auth/login_screen.dart';
import 'package:mobile/features/auth/login_service.dart';

void main() {
  testWidgets('valida correo y contraseña antes de enviar', (tester) async {
    final gateway = _FakeLoginGateway();
    await _pumpLogin(tester, gateway: gateway);

    await tester.tap(find.byKey(const Key('loginSubmitButton')));
    await tester.pump();

    expect(find.text('El correo electrónico es obligatorio.'), findsOneWidget);
    expect(find.text('La contraseña es obligatoria.'), findsOneWidget);
    expect(gateway.calls, 0);

    await tester.enterText(
      find.byKey(const Key('loginEmailField')),
      'correo-invalido',
    );
    await tester.pump();
    expect(find.text('Ingresa un correo electrónico válido.'), findsOneWidget);
  });

  testWidgets('normaliza correo, bloquea doble envío y completa el login', (
    tester,
  ) async {
    final completer = Completer<AuthenticatedUser>();
    final gateway = _FakeLoginGateway(handler: (_) => completer.future);
    AuthenticatedUser? authenticatedUser;
    await _pumpLogin(
      tester,
      gateway: gateway,
      onSuccess: (user) => authenticatedUser = user,
    );
    await _fillCredentials(tester);

    final submit = find.byKey(const Key('loginSubmitButton'));
    await tester.tap(submit);
    await tester.tap(submit);
    await tester.pump();

    expect(gateway.calls, 1);
    expect(gateway.lastRequest?.email, 'cliente@correo.com');
    expect(gateway.lastRequest?.password, 'clave-login');
    expect(find.byKey(const Key('loginLoading')), findsOneWidget);
    expect(tester.widget<FilledButton>(submit).onPressed, isNull);

    completer.complete(_client);
    await tester.pumpAndSettle();
    expect(authenticatedUser, same(_client));
    expect(find.byKey(const Key('loginLoading')), findsNothing);
  });

  testWidgets('muestra credenciales inválidas y permite reintentar', (
    tester,
  ) async {
    final gateway = _FakeLoginGateway(
      handler: (_) async => throw const LoginFailure(
        LoginFailureType.invalidCredentials,
        'Correo o contraseña incorrectos.',
      ),
    );
    await _pumpLogin(tester, gateway: gateway);
    await _fillCredentials(tester);

    await tester.tap(find.byKey(const Key('loginSubmitButton')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('loginError')), findsOneWidget);
    expect(find.text('Correo o contraseña incorrectos.'), findsOneWidget);
    expect(
      tester
          .widget<FilledButton>(find.byKey(const Key('loginSubmitButton')))
          .onPressed,
      isNotNull,
    );
  });

  testWidgets('muestra el error de conexión del servicio', (tester) async {
    final gateway = _FakeLoginGateway(
      handler: (_) async => throw const LoginFailure(
        LoginFailureType.connection,
        'No pudimos conectar con FashionStore. Revisa tu conexión.',
      ),
    );
    await _pumpLogin(tester, gateway: gateway);
    await _fillCredentials(tester);

    await tester.tap(find.byKey(const Key('loginSubmitButton')));
    await tester.pumpAndSettle();

    expect(find.textContaining('Revisa tu conexión'), findsOneWidget);
  });

  testWidgets('permite mostrar y ocultar la contraseña', (tester) async {
    await _pumpLogin(tester, gateway: _FakeLoginGateway());
    final field = find.byKey(const Key('loginPasswordField'));
    final editable = find.descendant(
      of: field,
      matching: find.byType(EditableText),
    );

    expect(tester.widget<EditableText>(editable).obscureText, isTrue);
    await tester.tap(find.byTooltip('Mostrar contraseña'));
    await tester.pump();
    expect(tester.widget<EditableText>(editable).obscureText, isFalse);
    await tester.tap(find.byTooltip('Ocultar contraseña'));
    await tester.pump();
    expect(tester.widget<EditableText>(editable).obscureText, isTrue);
  });

  testWidgets('expone enlaces de registro y recuperación sin llamar la API', (
    tester,
  ) async {
    var createAccountCalls = 0;
    var forgotPasswordCalls = 0;
    final gateway = _FakeLoginGateway();
    await _pumpLogin(
      tester,
      gateway: gateway,
      onCreateAccount: () => createAccountCalls++,
      onForgotPassword: () => forgotPasswordCalls++,
    );

    await tester.tap(find.byKey(const Key('forgotPasswordLink')));
    await tester.drag(
      find.byKey(const Key('loginScrollView')),
      const Offset(0, -180),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('createAccountLink')));
    await tester.pump();

    expect(forgotPasswordCalls, 1);
    expect(createAccountCalls, 1);
    expect(gateway.calls, 0);
  });

  for (final size in const [Size(320, 568), Size(390, 844), Size(600, 960)]) {
    testWidgets('no produce overflow en ${size.width.toInt()} px', (
      tester,
    ) async {
      tester.view.physicalSize = size;
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await _pumpLogin(tester, gateway: _FakeLoginGateway());
      await tester.drag(
        find.byKey(const Key('loginScrollView')),
        const Offset(0, -400),
      );
      await tester.pump();

      expect(tester.takeException(), isNull);
    });
  }
}

Future<void> _pumpLogin(
  WidgetTester tester, {
  required ClientLoginGateway gateway,
  ValueChanged<AuthenticatedUser>? onSuccess,
  VoidCallback? onCreateAccount,
  VoidCallback? onForgotPassword,
}) => tester.pumpWidget(
  MaterialApp(
    theme: AppTheme.light,
    home: LoginScreen(
      loginGateway: gateway,
      onLoginSuccess: onSuccess,
      onCreateAccount: onCreateAccount,
      onForgotPassword: onForgotPassword,
    ),
  ),
);

Future<void> _fillCredentials(WidgetTester tester) async {
  await tester.enterText(
    find.byKey(const Key('loginEmailField')),
    '  CLIENTE@CORREO.COM ',
  );
  await tester.enterText(
    find.byKey(const Key('loginPasswordField')),
    'clave-login',
  );
  await tester.pump();
}

const _client = AuthenticatedUser(
  userId: 42,
  firstName: 'Ana',
  lastName: 'Pérez',
  email: 'cliente@correo.com',
  role: 'CLIENTE',
);

class _FakeLoginGateway implements ClientLoginGateway {
  _FakeLoginGateway({this.handler});

  final Future<AuthenticatedUser> Function(LoginRequest request)? handler;
  int calls = 0;
  LoginRequest? lastRequest;

  @override
  Future<AuthenticatedUser> login(LoginRequest request) {
    calls++;
    lastRequest = request;
    return handler?.call(request) ?? Future.value(_client);
  }
}
