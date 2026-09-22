import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mobile/core/services/api_service.dart';
import 'package:mobile/core/storage/token_storage.dart';
import 'package:mobile/features/chatbot/chatbot_models.dart';
import 'package:mobile/features/chatbot/chatbot_service.dart';

void main() {
  test('envía una pregunta y recibe respuesta del asistente CU27', () async {
    late http.Request request;
    final service = ChatbotService(
      apiService: ApiService(
        client: MockClient((value) async {
          request = value;
          return http.Response(
            jsonEncode({
              'success': true,
              'data': {
                'reply': 'Encontré un vestido rojo disponible en talla M.',
                'products': [
                  {
                    'id_producto': 7,
                    'nombre': 'Vestido rojo de fiesta',
                    'categoria': 'Vestidos',
                    'precio': '200.00',
                    'colores': ['Rojo'],
                    'tallas': ['M'],
                    'disponibilidad': 'DISPONIBLE',
                    'cantidad_disponible': 3,
                  },
                ],
              },
            }),
            200,
          );
        }),
        tokenStorage: _TokenStorage(),
      ),
    );

    final response = await service.sendMessage(
      message: 'Busco un vestido rojo para una fiesta',
      history: const [
        ChatMessage(
          role: ChatMessageRole.user,
          content: 'Necesito ropa para una fiesta',
        ),
      ],
    );

    expect(request.method, 'POST');
    expect(request.url.path, '/api/client/chatbot/message');
    expect(request.headers['authorization'], 'Bearer jwt');
    expect(jsonDecode(request.body)['history'], isNotEmpty);
    expect(response.reply, contains('vestido rojo'));
    expect(response.products.single.name, 'Vestido rojo de fiesta');
  });
}

class _TokenStorage implements TokenStorage {
  @override
  Future<void> deleteToken() async {}

  @override
  Future<String?> getToken() async => 'jwt';

  @override
  Future<void> saveToken(String token) async {}
}
