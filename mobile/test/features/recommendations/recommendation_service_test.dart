import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mobile/core/services/api_service.dart';
import 'package:mobile/core/storage/token_storage.dart';
import 'package:mobile/features/recommendations/recommendation_service.dart';

void main() {
  test('consulta recomendaciones CU26', () async {
    late http.Request request;
    final service = RecommendationService(
      apiService: ApiService(
        client: MockClient((value) async {
          request = value;
          return http.Response(jsonEncode({
            'success': true,
            'data': [
              {
                'id_producto': 7,
                'nombre': 'Camisa Oxford',
                'descripcion_corta': 'Camisa ligera',
                'seccion': 'UNISEX',
                'id_categoria': 2,
                'categoria': 'Camisas',
                'precio_base': 180,
                'precio_final': 160,
                'tiene_promocion': true,
                'imagen_principal': null,
                'variante_sugerida': {
                  'id_variante_producto': 15,
                  'sku': 'CAM-M-AZ',
                  'id_talla': 2,
                  'talla': 'M',
                  'id_color': 4,
                  'color': 'Azul',
                  'codigo_hex': '#112233',
                  'stock_disponible': 4,
                },
                'motivo': 'Popular entre clientes similares',
                'ya_comprado': false,
              },
            ],
            'origen': 'FALLBACK',
          }), 200);
        }),
        tokenStorage: _TokenStorage(),
      ),
    );

    final page = await service.loadRecommendations();

    expect(request.method, 'GET');
    expect(request.url.path, '/api/client/recommendations');
    expect(request.url.queryParameters['limit'], '12');
    expect(page.items.single.name, 'Camisa Oxford');
    expect(page.items.single.suggestedVariant!.availableStock, 4);
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
