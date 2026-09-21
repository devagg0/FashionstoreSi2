import '../catalog/catalog_models.dart';

class CartItem {
  const CartItem({
    required this.idCartDetail,
    required this.variantId,
    required this.productId,
    required this.productName,
    required this.sku,
    required this.size,
    required this.color,
    required this.imageUrl,
    required this.quantity,
    required this.basePrice,
    required this.finalPrice,
    required this.promotion,
    required this.subtotal,
    required this.availability,
    required this.productActive,
    required this.variantActive,
  });

  final int idCartDetail;
  final int variantId;
  final int productId;
  final String productName;
  final String sku;
  final CatalogSize size;
  final CatalogColor color;
  final String? imageUrl;
  final int quantity;
  final double basePrice;
  final double finalPrice;
  final CatalogPromotion? promotion;
  final double subtotal;
  final int availability;
  final bool productActive;
  final bool variantActive;

  factory CartItem.fromJson(Map<String, dynamic> json) => CartItem(
    idCartDetail: _requiredInt(json, 'id_detalle_carrito'),
    variantId: _requiredInt(json, 'id_variante_producto'),
    productId: _requiredInt(json, 'id_producto'),
    productName: _requiredString(json, 'nombre_producto'),
    sku: _requiredString(json, 'sku'),
    size: _requiredObject(json, 'talla', CatalogSize.fromJson),
    color: _requiredObject(json, 'color', CatalogColor.fromJson),
    imageUrl: _optionalString(json['imagen_principal']),
    quantity: _requiredInt(json, 'cantidad'),
    basePrice: _requiredDouble(json, 'precio_base'),
    finalPrice: _requiredDouble(json, 'precio_final'),
    promotion: _optionalObject(json['promocion'], CatalogPromotion.fromJson),
    subtotal: _requiredDouble(json, 'subtotal_linea'),
    availability: _requiredInt(json, 'disponibilidad_actual'),
    productActive: _requiredBool(json, 'estado_producto'),
    variantActive: _requiredBool(json, 'estado_variante'),
  );
}

class CartData {
  const CartData({
    this.idCarrito,
    this.state,
    required this.items,
    required this.quantityItems,
    required this.quantityUnits,
    required this.subtotal,
    required this.discountTotal,
    required this.total,
  });

  final int? idCarrito;
  final String? state;
  final List<CartItem> items;
  final int quantityItems;
  final int quantityUnits;
  final double subtotal;
  final double discountTotal;
  final double total;

  factory CartData.fromJson(Map<String, dynamic> json) => CartData(
    idCarrito: json['id_carrito'] is int ? json['id_carrito'] as int : null,
    state: json['estado'] is String ? json['estado'] as String : null,
    items: _requiredList(json, 'items', CartItem.fromJson),
    quantityItems: _requiredInt(json, 'cantidad_items'),
    quantityUnits: _requiredInt(json, 'cantidad_unidades'),
    subtotal: _requiredDouble(json, 'subtotal'),
    discountTotal: _requiredDouble(json, 'descuento_total'),
    total: _requiredDouble(json, 'total'),
  );
}

enum CartFailureType {
  unauthorized,
  forbidden,
  notFound,
  conflict,
  invalidData,
  timeout,
  connection,
  server,
  invalidResponse,
}

class CartFailure implements Exception {
  const CartFailure(this.type, this.message);

  final CartFailureType type;
  final String message;

  bool get invalidatesSession =>
      type == CartFailureType.unauthorized ||
      type == CartFailureType.forbidden;

  @override
  String toString() => 'CartFailure($type): $message';
}

int _requiredInt(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is int) return value;
  throw FormatException('$key inválido.');
}

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

String? _optionalString(Object? value) {
  if (value == null) return null;
  if (value is! String) throw const FormatException('Texto inválido.');
  return value.trim().isEmpty ? null : value.trim();
}

bool _requiredBool(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is bool) return value;
  throw FormatException('$key inválido.');
}

T _requiredObject<T>(Map<String, dynamic> json, String key, T Function(Map<String, dynamic>) parser) {
  final value = json[key];
  if (value is! Map<String, dynamic>) {
    throw FormatException('$key inválido.');
  }
  return parser(value);
}

T? _optionalObject<T>(Object? value, T Function(Map<String, dynamic>) parser) {
  if (value == null) return null;
  if (value is! Map<String, dynamic>) {
    throw const FormatException('Objeto inválido.');
  }
  return parser(value);
}

List<T> _requiredList<T>(Map<String, dynamic> json, String key, T Function(Map<String, dynamic>) parser) {
  final value = json[key];
  if (value is! List) {
    throw FormatException('$key inválido.');
  }
  return value
      .map((item) {
        if (item is! Map<String, dynamic>) {
          throw const FormatException('Item inválido.');
        }
        return parser(item);
      })
      .toList(growable: false);
}
