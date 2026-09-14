import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/main.dart';
import 'package:mobile/features/auth/login_models.dart';
import 'package:mobile/features/auth/login_screen.dart';
import 'package:mobile/features/auth/login_service.dart';

void main() {
  testWidgets('FashionStore presenta el acceso de cliente', (tester) async {
    await tester.pumpWidget(
      MyApp(home: LoginScreen(loginGateway: _NoopLoginGateway())),
    );

    expect(find.text('FASHIONSTORE'), findsOneWidget);
    expect(find.text('Inicia sesión'), findsOneWidget);
    expect(find.text('¿Olvidaste tu contraseña?'), findsOneWidget);
    expect(find.byKey(const Key('loginSubmitButton')), findsOneWidget);
  });
}

class _NoopLoginGateway implements ClientLoginGateway {
  @override
  Future<AuthenticatedUser> login(LoginRequest request) {
    throw UnimplementedError();
  }
}
