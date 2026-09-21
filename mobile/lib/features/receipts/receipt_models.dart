class SaleReceipt {
  const SaleReceipt({
    required this.saleCode,
    required this.completedDate,
    required this.channel,
    required this.branch,
    required this.client,
    required this.products,
    required this.subtotal,
    required this.discountTotal,
    required this.total,
    required this.currency,
    required this.payment,
  });

  final String saleCode;
  final DateTime? completedDate;
  final String channel;
  final ReceiptBranch branch;
  final ReceiptClient? client;
  final List<ReceiptItem> products;
  final double subtotal;
  final double discountTotal;
  final double total;
  final String currency;
  final ReceiptPayment payment;

  factory SaleReceipt.fromJson(Map<String, dynamic> json) => SaleReceipt(
    saleCode: _requiredString(json, 'numero_venta'),
    completedDate: _date(json['fecha_completada']),
    channel: _requiredString(json, 'canal'),
    branch: ReceiptBranch.fromJson(_requiredMap(json, 'sucursal')),
    client: _optionalObject(json['cliente'], ReceiptClient.fromJson),
    products: _requiredList(json, 'productos', ReceiptItem.fromJson),
    subtotal: _double(json, 'subtotal'),
    discountTotal: _double(json, 'descuento_total'),
    total: _double(json, 'total'),
    currency: _requiredString(json, 'moneda'),
    payment: ReceiptPayment.fromJson(_requiredMap(json, 'pago')),
  );
}

class ReceiptBranch {
  const ReceiptBranch({required this.name, required this.address});
  final String name;
  final String address;

  factory ReceiptBranch.fromJson(Map<String, dynamic> json) => ReceiptBranch(
    name: _requiredString(json, 'nombre'),
    address: _requiredString(json, 'direccion'),
  );
}

class ReceiptClient {
  const ReceiptClient({required this.name, required this.lastName});
  final String name;
  final String lastName;

  factory ReceiptClient.fromJson(Map<String, dynamic> json) => ReceiptClient(
    name: _requiredString(json, 'nombre'),
    lastName: _requiredString(json, 'apellido'),
  );
}

class ReceiptItem {
  const ReceiptItem({
    required this.name,
    required this.size,
    required this.color,
    required this.quantity,
    required this.unitPrice,
    required this.unitDiscount,
    required this.lineSubtotal,
  });

  final String? name;
  final String? size;
  final String? color;
  final int quantity;
  final double unitPrice;
  final double unitDiscount;
  final double lineSubtotal;

  factory ReceiptItem.fromJson(Map<String, dynamic> json) => ReceiptItem(
    name: _optionalString(json['nombre']),
    size: _optionalString(json['talla']),
    color: _optionalString(json['color']),
    quantity: _int(json, 'cantidad'),
    unitPrice: _double(json, 'precio_unitario'),
    unitDiscount: _double(json, 'descuento_unitario'),
    lineSubtotal: _double(json, 'subtotal_linea'),
  );
}

class ReceiptPayment {
  const ReceiptPayment({required this.method, required this.state, required this.amount});
  final String method;
  final String state;
  final double amount;

  factory ReceiptPayment.fromJson(Map<String, dynamic> json) => ReceiptPayment(
    method: _requiredString(json, 'medio'),
    state: _requiredString(json, 'estado'),
    amount: _double(json, 'monto'),
  );
}

enum ReceiptFailureType { unauthorized, forbidden, notFound, conflict, timeout, connection, invalidResponse, server }

class ReceiptFailure implements Exception {
  const ReceiptFailure(this.type, this.message);
  final ReceiptFailureType type;
  final String message;
  bool get invalidatesSession => type == ReceiptFailureType.unauthorized;
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

String _requiredString(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is! String || value.trim().isEmpty) throw FormatException('$key inválido.');
  return value.trim();
}

String? _optionalString(Object? value) {
  if (value == null) return null;
  if (value is! String) throw const FormatException('Texto inválido.');
  return value.trim().isEmpty ? null : value.trim();
}

DateTime? _date(Object? value) => value is String ? DateTime.tryParse(value) : null;

Map<String, dynamic> _requiredMap(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is! Map<String, dynamic>) throw FormatException('$key inválido.');
  return value;
}

T? _optionalObject<T>(Object? value, T Function(Map<String, dynamic>) parser) {
  if (value == null) return null;
  if (value is! Map<String, dynamic>) throw const FormatException('Objeto inválido.');
  return parser(value);
}

List<T> _requiredList<T>(Map<String, dynamic> json, String key, T Function(Map<String, dynamic>) parser) {
  final value = json[key];
  if (value is! List) throw FormatException('$key inválido.');
  return value.map((item) {
    if (item is! Map<String, dynamic>) throw const FormatException('Item inválido.');
    return parser(item);
  }).toList(growable: false);
}
