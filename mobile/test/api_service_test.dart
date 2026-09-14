import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mobile/core/config/api_config.dart';
import 'package:mobile/core/errors/api_exception.dart';
import 'package:mobile/core/services/api_service.dart';
import 'package:mobile/core/storage/token_storage.dart';

void main() {
  test(
    'ApiConfig usa una URL válida y construye rutas sin duplicar barras',
    () {
      expect(ApiConfig.baseUri.host, isNotEmpty);
      expect(ApiConfig.uriFor('/health').path, '/health');
    },
  );

  test(
    'GET agrega query parameters y el Bearer token automáticamente',
    () async {
      final client = MockClient((request) async {
        expect(request.method, 'GET');
        expect(request.url.path, '/api/catalog/products');
        expect(request.url.queryParameters, {'page': '1'});
        expect(request.headers['authorization'], 'Bearer jwt-seguro');
        expect(request.headers['x-client'], 'mobile');
        return http.Response(jsonEncode({'success': true}), 200);
      });
      final api = ApiService(
        client: client,
        tokenStorage: _MemoryTokenStorage('jwt-seguro'),
      );

      final response = await api.get(
        '/api/catalog/products',
        queryParameters: {'page': '1'},
        headers: {'X-Client': 'mobile'},
      );

      expect(response, {'success': true});
    },
  );

  test('POST, PUT, PATCH y DELETE envían JSON', () async {
    final methods = <String>[];
    final client = MockClient((request) async {
      methods.add(request.method);
      expect(jsonDecode(request.body), {'id': 1});
      return http.Response('{}', 200);
    });
    final api = ApiService(client: client, tokenStorage: _MemoryTokenStorage());

    await api.post('/api/client/cart/items', {'id': 1}, includeAuth: false);
    await api.put('/api/auth/change-password', {'id': 1}, includeAuth: false);
    await api.patch('/api/client/cart/items/1', {'id': 1}, includeAuth: false);
    await api.delete(
      '/api/client/cart/items/1',
      data: {'id': 1},
      includeAuth: false,
    );

    expect(methods, ['POST', 'PUT', 'PATCH', 'DELETE']);
  });

  test('convierte errores HTTP JSON en ApiException', () async {
    final api = ApiService(
      client: MockClient(
        (_) async =>
            http.Response(jsonEncode({'detail': 'No autorizado'}), 401),
      ),
      tokenStorage: _MemoryTokenStorage(),
    );

    expect(
      () => api.get('/api/client/cart'),
      throwsA(
        isA<ApiException>()
            .having((error) => error.statusCode, 'statusCode', 401)
            .having((error) => error.message, 'message', 'No autorizado'),
      ),
    );
  });

  test('convierte esperas excesivas en ApiTimeoutException', () async {
    final api = ApiService(
      client: MockClient((_) async {
        await Future<void>.delayed(const Duration(milliseconds: 30));
        return http.Response('{}', 200);
      }),
      tokenStorage: _MemoryTokenStorage(),
      timeout: const Duration(milliseconds: 1),
    );

    expect(
      () => api.get('/health', includeAuth: false),
      throwsA(isA<ApiTimeoutException>()),
    );
  });
}

class _MemoryTokenStorage implements TokenStorage {
  _MemoryTokenStorage([this.token]);

  String? token;

  @override
  Future<void> deleteToken() async => token = null;

  @override
  Future<String?> getToken() async => token;

  @override
  Future<void> saveToken(String token) async => this.token = token;
}
