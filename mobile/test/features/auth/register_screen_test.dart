import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/core/theme/app_theme.dart';
import 'package:mobile/features/auth/register_screen.dart';
import 'package:mobile/features/auth/registration_models.dart';
import 'package:mobile/features/auth/registration_service.dart';

void main() {
  testWidgets('muestra validaciones locales sin enviar datos', (tester) async {
    final gateway = _FakeRegistrationGateway();
    await _pumpScreen(tester, gateway);

    await _scrollToSubmit(tester);
    await tester.tap(find.byKey(const Key('registerSubmitButton')));
    await tester.pump();

    expect(find.text('El nombre es obligatorio.'), findsOneWidget);
    expect(find.text('El apellido es obligatorio.'), findsOneWidget);
    expect(find.text('El correo electrónico es obligatorio.'), findsOneWidget);
    expect(find.text('La contraseña es obligatoria.'), findsOneWidget);
    expect(find.text('Confirma tu contraseña.'), findsOneWidget);
    expect(gateway.calls, 0);
  });

  testWidgets('loading bloquea doble envío y luego muestra éxito', (
    tester,
  ) async {
    final completer = Completer<ClientRegistrationResult>();
    final gateway = _FakeRegistrationGateway(handler: (_) => completer.future);
    await _pumpScreen(tester, gateway);
    await _fillValidForm(tester);

    final submit = find.byKey(const Key('registerSubmitButton'));
    await _scrollToSubmit(tester);
    await tester.tap(submit);
    await tester.tap(submit);
    await tester.pump();

    expect(gateway.calls, 1);
    expect(gateway.lastRequest?.firstName, 'Ana');
    expect(gateway.lastRequest?.lastName, 'Pérez');
    expect(gateway.lastRequest?.email, 'ana@correo.com');
    expect(gateway.lastRequest?.phone, '70012345');
    expect(find.byKey(const Key('registrationLoading')), findsOneWidget);
    final button = tester.widget<FilledButton>(submit);
    expect(button.onPressed, isNull);

    completer.complete(_successResult);
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('registrationSuccess')), findsOneWidget);
    expect(find.text('Cuenta creada correctamente'), findsOneWidget);
    expect(find.textContaining('ana@correo.com'), findsOneWidget);
  });

  testWidgets('correo duplicado se muestra junto al campo de correo', (
    tester,
  ) async {
    final gateway = _FakeRegistrationGateway(
      handler: (_) async => throw const RegistrationFailure(
        RegistrationFailureType.duplicateEmail,
        'Este correo ya se encuentra registrado.',
      ),
    );
    await _pumpScreen(tester, gateway);
    await _fillValidForm(tester);

    await _scrollToSubmit(tester);
    await tester.tap(find.byKey(const Key('registerSubmitButton')));
    await tester.pumpAndSettle();

    expect(
      find.text('Este correo ya se encuentra registrado.'),
      findsOneWidget,
    );
  });

  testWidgets('permite mostrar y volver a ocultar la contraseña', (
    tester,
  ) async {
    await _pumpScreen(tester, _FakeRegistrationGateway());
    final field = find.byKey(const Key('registerPasswordField'));
    await tester.scrollUntilVisible(
      field,
      280,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pumpAndSettle();

    final editableText = find.descendant(
      of: field,
      matching: find.byType(EditableText),
    );
    expect(tester.widget<EditableText>(editableText).obscureText, isTrue);
    await tester.tap(find.byTooltip('Mostrar contraseña'));
    await tester.pump();
    expect(tester.widget<EditableText>(editableText).obscureText, isFalse);
    await tester.tap(find.byTooltip('Ocultar contraseña'));
    await tester.pump();
    expect(tester.widget<EditableText>(editableText).obscureText, isTrue);
  });

  testWidgets('error de conexión muestra un estado visible y recuperable', (
    tester,
  ) async {
    final gateway = _FakeRegistrationGateway(
      handler: (_) async => throw const RegistrationFailure(
        RegistrationFailureType.connection,
        'No pudimos conectar con FashionStore. Revisa tu conexión.',
      ),
    );
    await _pumpScreen(tester, gateway);
    await _fillValidForm(tester);

    await _scrollToSubmit(tester);
    await tester.tap(find.byKey(const Key('registerSubmitButton')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('registrationError')), findsOneWidget);
    expect(find.textContaining('Revisa tu conexión'), findsOneWidget);
    expect(
      tester
          .widget<FilledButton>(find.byKey(const Key('registerSubmitButton')))
          .onPressed,
      isNotNull,
    );
  });

  for (final size in const [Size(320, 568), Size(390, 844), Size(600, 960)]) {
    testWidgets('no produce overflow en ${size.width.toInt()} px', (
      tester,
    ) async {
      tester.view.physicalSize = size;
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await _pumpScreen(tester, _FakeRegistrationGateway());
      await tester.drag(find.byType(CustomScrollView), const Offset(0, -500));
      await tester.pump();

      final exception = tester.takeException();
      expect(
        exception,
        isNull,
        reason: exception is FlutterError
            ? exception.toStringDeep()
            : exception.toString(),
      );
    });
  }
}

Future<void> _pumpScreen(
  WidgetTester tester,
  ClientRegistrationGateway gateway,
) => tester.pumpWidget(
  MaterialApp(
    theme: AppTheme.light,
    home: RegisterScreen(registrationGateway: gateway),
  ),
);

Future<void> _fillValidForm(WidgetTester tester) async {
  await tester.enterText(
    find.byKey(const Key('registerFirstNameField')),
    '  Ana  ',
  );
  await tester.enterText(
    find.byKey(const Key('registerLastNameField')),
    '  Pérez  ',
  );
  await tester.enterText(
    find.byKey(const Key('registerEmailField')),
    '  ANA@CORREO.COM  ',
  );
  await tester.enterText(
    find.byKey(const Key('registerPhoneField')),
    ' 70012345 ',
  );
  await tester.enterText(
    find.byKey(const Key('registerPasswordField')),
    'Fashion@2026',
  );
  await tester.enterText(
    find.byKey(const Key('registerConfirmationField')),
    'Fashion@2026',
  );
  await tester.pump();
}

Future<void> _scrollToSubmit(WidgetTester tester) async {
  await tester.scrollUntilVisible(
    find.byKey(const Key('registerSubmitButton')),
    320,
    scrollable: find.byType(Scrollable).first,
  );
  await tester.pumpAndSettle();
}

const _successResult = ClientRegistrationResult(
  message: 'Cliente registrado correctamente',
  client: RegisteredClient(
    userId: 42,
    firstName: 'Ana',
    lastName: 'Pérez',
    email: 'ana@correo.com',
  ),
);

class _FakeRegistrationGateway implements ClientRegistrationGateway {
  _FakeRegistrationGateway({this.handler});

  final Future<ClientRegistrationResult> Function(
    ClientRegistrationRequest request,
  )?
  handler;
  int calls = 0;
  ClientRegistrationRequest? lastRequest;

  @override
  Future<ClientRegistrationResult> register(ClientRegistrationRequest request) {
    calls++;
    lastRequest = request;
    return handler?.call(request) ?? Future.value(_successResult);
  }
}
