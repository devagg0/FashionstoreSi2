import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/core/config/api_config.dart';
import 'package:mobile/core/services/api_service.dart';

const runLiveApiTest = bool.fromEnvironment('RUN_LIVE_API_TEST');

void main() {
  test(
    'Render responde desde ApiService mediante su endpoint público /health',
    () async {
      // Render can need extra time when the service wakes from an idle state.
      final api = ApiService(timeout: const Duration(seconds: 60));
      addTearDown(api.close);

      final response = await api.get('/health', includeAuth: false);

      expect(response, {'status': 'ok'});
      // Makes the selected target explicit in verbose test output and failures.
      expect(ApiConfig.baseUri.scheme, 'https');
    },
    skip: runLiveApiTest
        ? false
        : 'Prueba externa; habilitar con RUN_LIVE_API_TEST=true.',
  );
}
