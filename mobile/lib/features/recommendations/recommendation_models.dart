import '../catalog/catalog_models.dart';

class RecommendationItem {
  const RecommendationItem({
    required this.productId,
    required this.name,
    required this.shortDescription,
    required this.section,
    required this.category,
    required this.basePrice,
    required this.finalPrice,
    required this.hasPromotion,
    required this.primaryImage,
    required this.suggestedVariant,
    required this.reason,
    required this.alreadyPurchased,
  });

  final int productId;
  final String name;
  final String? shortDescription;
  final CatalogSection section;
  final String category;
  final double basePrice;
  final double finalPrice;
  final bool hasPromotion;
  final String? primaryImage;
  final RecommendationVariant? suggestedVariant;
  final String reason;
  final bool alreadyPurchased;

  factory RecommendationItem.fromJson(Map<String, dynamic> json) => RecommendationItem(
    productId: _int(json, 'id_producto'),
    name: _string(json, 'nombre'),
    shortDescription: _optionalString(json['descripcion_corta']),
    section: CatalogSection.parse(_string(json, 'seccion')),
    category: _string(json, 'categoria'),
    basePrice: _double(json, 'precio_base'),
    finalPrice: _double(json, 'precio_final'),
    hasPromotion: _bool(json, 'tiene_promocion'),
    primaryImage: _optionalString(json['imagen_principal']),
    suggestedVariant: _optionalObject(json['variante_sugerida'], RecommendationVariant.fromJson),
    reason: _string(json, 'motivo'),
    alreadyPurchased: _bool(json, 'ya_comprado'),
  );
}

class RecommendationVariant {
  const RecommendationVariant({
    required this.variantId,
    required this.sku,
    required this.size,
    required this.color,
    required this.hexCode,
    required this.availableStock,
  });

  final int variantId;
  final String sku;
  final String size;
  final String color;
  final String? hexCode;
  final int availableStock;

  factory RecommendationVariant.fromJson(Map<String, dynamic> json) => RecommendationVariant(
    variantId: _int(json, 'id_variante_producto'),
    sku: _string(json, 'sku'),
    size: _string(json, 'talla'),
    color: _string(json, 'color'),
    hexCode: _optionalString(json['codigo_hex']),
    availableStock: _int(json, 'stock_disponible'),
  );
}

enum RecommendationFailureType { unauthorized, forbidden, notFound, invalidData, timeout, connection, invalidResponse, server }

class RecommendationFailure implements Exception {
  const RecommendationFailure(this.type, this.message);
  final RecommendationFailureType type;
  final String message;
  bool get invalidatesSession => type == RecommendationFailureType.unauthorized;
}

int _int(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is int) return value;
  throw FormatException('$key inválido.');
}

double _double(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is num) return value.toDouble();
  if (value is String) {
    final parsed = double.tryParse(value);
    if (parsed != null) return parsed;
  }
  throw FormatException('$key inválido.');
}

String _string(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is! String || value.trim().isEmpty) throw FormatException('$key inválido.');
  return value.trim();
}

String? _optionalString(Object? value) => value is String && value.trim().isNotEmpty ? value.trim() : null;

bool _bool(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is bool) return value;
  throw FormatException('$key inválido.');
}

T? _optionalObject<T>(Object? value, T Function(Map<String, dynamic>) parser) {
  if (value == null) return null;
  if (value is! Map<String, dynamic>) throw const FormatException('Objeto inválido.');
  return parser(value);
}
