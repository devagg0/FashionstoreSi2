class DigitalSaleItem {
  const DigitalSaleItem({
    required this.variantId,
    required this.promotionId,
    required this.quantity,
    required this.unitPrice,
    required this.unitDiscount,
    required this.lineSubtotal,
  });

  final int variantId;
  final int? promotionId;
  final int quantity;
  final double unitPrice;
  final double unitDiscount;
  final double lineSubtotal;

  factory DigitalSaleItem.fromJson(Map<String, dynamic> json) => DigitalSaleItem(
    variantId: _requiredInt(json, 'id_variante_producto'),
    promotionId: json['id_promocion'] is int ? json['id_promocion'] as int : null,
    quantity: _requiredInt(json, 'cantidad'),
    unitPrice: _requiredDouble(json, 'precio_unitario'),
    unitDiscount: _requiredDouble(json, 'descuento_unitario'),
    lineSubtotal: _requiredDouble(json, 'subtotal_linea'),
  );
}

class DigitalSale {
  const DigitalSale({
    required this.saleId,
    required this.purchaseCode,
    required this.clientId,
    required this.cartId,
    required this.branchId,
    required this.channel,
    required this.currency,
    required this.state,
    required this.stockCommitted,
    required this.paymentExpiration,
    required this.subtotal,
    required this.discountTotal,
    required this.total,
    required this.items,
  });

  final int saleId;
  final String purchaseCode;
  final int clientId;
  final int cartId;
  final int branchId;
  final String channel;
  final String currency;
  final String state;
  final bool stockCommitted;
  final DateTime? paymentExpiration;
  final double subtotal;
  final double discountTotal;
  final double total;
  final List<DigitalSaleItem> items;

  factory DigitalSale.fromJson(Map<String, dynamic> json) => DigitalSale(
    saleId: _requiredInt(json, 'id_venta'),
    purchaseCode: _requiredString(json, 'numero_venta'),
    clientId: _requiredInt(json, 'id_cliente'),
    cartId: _requiredInt(json, 'id_carrito'),
    branchId: _requiredInt(json, 'id_sucursal'),
    channel: _requiredString(json, 'canal'),
    currency: _requiredString(json, 'moneda'),
    state: _requiredString(json, 'estado'),
    stockCommitted: _requiredBool(json, 'stock_comprometido'),
    paymentExpiration: _optionalDate(json['fecha_expiracion_pago']),
    subtotal: _requiredDouble(json, 'subtotal'),
    discountTotal: _requiredDouble(json, 'descuento_total'),
    total: _requiredDouble(json, 'total'),
    items: _requiredList(json, 'items', DigitalSaleItem.fromJson),
  );
}

class CheckoutFailure implements Exception {
  const CheckoutFailure(this.type, this.message);

  final CheckoutFailureType type;
  final String message;

  bool get invalidatesSession => type == CheckoutFailureType.unauthorized;
}

enum CheckoutFailureType {
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

class CheckoutResponseData {
  const CheckoutResponseData({required this.sale, required this.message});

  final DigitalSale sale;
  final String message;
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

bool _requiredBool(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is bool) return value;
  throw FormatException('$key inválido.');
}

DateTime? _optionalDate(Object? value) {
  if (value == null) return null;
  if (value is! String) throw const FormatException('Fecha inválida.');
  return DateTime.tryParse(value);
}

List<T> _requiredList<T>(
  Map<String, dynamic> json,
  String key,
  T Function(Map<String, dynamic>) parser,
) {
  final value = json[key];
  if (value is! List) throw FormatException('$key inválido.');
  return value.map((item) {
    if (item is! Map<String, dynamic>) throw const FormatException('Item inválido.');
    return parser(item);
  }).toList(growable: false);
}
