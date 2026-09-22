class ChatMessage {
  const ChatMessage({required this.role, required this.content});

  final ChatMessageRole role;
  final String content;
}

enum ChatMessageRole { user, assistant }

class ChatbotProduct {
  const ChatbotProduct({
    required this.productId,
    required this.name,
    required this.category,
    required this.price,
    required this.colors,
    required this.sizes,
    required this.availability,
    required this.availableQuantity,
  });

  final int productId;
  final String name;
  final String category;
  final double price;
  final List<String> colors;
  final List<String> sizes;
  final String? availability;
  final int? availableQuantity;

  factory ChatbotProduct.fromJson(Map<String, dynamic> json) => ChatbotProduct(
    productId: _requiredInt(json, 'id_producto'),
    name: _requiredString(json, 'nombre'),
    category: _requiredString(json, 'categoria'),
    price: _requiredDouble(json, 'precio'),
    colors: _requiredStrings(json, 'colores'),
    sizes: _requiredStrings(json, 'tallas'),
    availability: _optionalString(json['disponibilidad']),
    availableQuantity: _optionalInt(json['cantidad_disponible']),
  );
}

class ChatbotResponse {
  const ChatbotResponse({required this.reply, required this.products});

  final String reply;
  final List<ChatbotProduct> products;

  factory ChatbotResponse.fromJson(Map<String, dynamic> json) {
    if (json['success'] != true || json['data'] is! Map<String, dynamic>) {
      throw const FormatException('Respuesta del asistente inválida.');
    }
    final data = json['data'] as Map<String, dynamic>;
    final reply = data['reply'];
    final rawProducts = data['products'];
    if (reply is! String || reply.trim().isEmpty || rawProducts is! List) {
      throw const FormatException('Respuesta del asistente incompleta.');
    }
    return ChatbotResponse(
      reply: reply.trim(),
      products: rawProducts
          .map((item) {
            if (item is! Map<String, dynamic>) {
              throw const FormatException('Producto sugerido inválido.');
            }
            return ChatbotProduct.fromJson(item);
          })
          .toList(growable: false),
    );
  }
}

enum ChatbotFailureType {
  unauthorized,
  forbidden,
  timeout,
  connection,
  invalidResponse,
  server,
}

class ChatbotFailure implements Exception {
  const ChatbotFailure(this.type, this.message);

  final ChatbotFailureType type;
  final String message;

  bool get invalidatesSession => type == ChatbotFailureType.unauthorized;
}

int _requiredInt(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is int) return value;
  throw FormatException('$key inválido.');
}

int? _optionalInt(Object? value) => value is int ? value : null;

double _requiredDouble(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is num) return value.toDouble();
  if (value is String) {
    final parsed = double.tryParse(value);
    if (parsed != null) return parsed;
  }
  throw FormatException('$key inválido.');
}

String _requiredString(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is! String || value.trim().isEmpty) {
    throw FormatException('$key inválido.');
  }
  return value.trim();
}

String? _optionalString(Object? value) =>
    value is String && value.trim().isNotEmpty ? value.trim() : null;

List<String> _requiredStrings(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is! List || value.any((item) => item is! String)) {
    throw FormatException('$key inválido.');
  }
  return value.map((item) => (item as String).trim()).toList(growable: false);
}
