class PurchaseSummary {
  const PurchaseSummary({
    required this.saleId,
    required this.purchaseCode,
    required this.date,
    required this.completedDate,
    required this.channel,
    required this.state,
    required this.subtotal,
    required this.discountTotal,
    required this.total,
    required this.currency,
    required this.branch,
    required this.payment,
  });

  final int saleId;
  final String purchaseCode;
  final DateTime? date;
  final DateTime? completedDate;
  final String channel;
  final String state;
  final double subtotal;
  final double discountTotal;
  final double total;
  final String currency;
  final PurchaseBranch branch;
  final PurchasePayment? payment;

  factory PurchaseSummary.fromJson(Map<String, dynamic> json) => PurchaseSummary(
    saleId: _requiredInt(json, 'id_venta'),
    purchaseCode: _requiredString(json, 'numero_venta'),
    date: _date(json['fecha']),
    completedDate: _date(json['fecha_completada']),
    channel: _requiredString(json, 'canal'),
    state: _requiredString(json, 'estado'),
    subtotal: _requiredDouble(json, 'subtotal'),
    discountTotal: _requiredDouble(json, 'descuento_total'),
    total: _requiredDouble(json, 'total'),
    currency: _requiredString(json, 'moneda'),
    branch: PurchaseBranch.fromJson(_requiredMap(json, 'sucursal')),
    payment: _optionalObject(json['pago'], PurchasePayment.fromJson),
  );
}

class PurchaseDetail extends PurchaseSummary {
  const PurchaseDetail({
    required super.saleId,
    required super.purchaseCode,
    required super.date,
    required super.completedDate,
    required super.channel,
    required super.state,
    required super.subtotal,
    required super.discountTotal,
    required super.total,
    required super.currency,
    required super.branch,
    required super.payment,
    required this.products,
    required this.payments,
    required this.returns,
  });

  final List<PurchaseItem> products;
  final List<PurchasePayment> payments;
  final List<PurchaseReturn> returns;

  factory PurchaseDetail.fromJson(Map<String, dynamic> json) => PurchaseDetail(
    saleId: _requiredInt(json, 'id_venta'),
    purchaseCode: _requiredString(json, 'numero_venta'),
    date: _date(json['fecha']),
    completedDate: _date(json['fecha_completada']),
    channel: _requiredString(json, 'canal'),
    state: _requiredString(json, 'estado'),
    subtotal: _requiredDouble(json, 'subtotal'),
    discountTotal: _requiredDouble(json, 'descuento_total'),
    total: _requiredDouble(json, 'total'),
    currency: _requiredString(json, 'moneda'),
    branch: PurchaseBranch.fromJson(_requiredMap(json, 'sucursal')),
    payment: _optionalObject(json['pago'], PurchasePayment.fromJson),
    products: _requiredList(json, 'productos', PurchaseItem.fromJson),
    payments: _requiredList(json, 'pagos', PurchasePayment.fromJson),
    returns: _requiredList(json, 'devoluciones', PurchaseReturn.fromJson),
  );
}

class PurchaseReturn {
  const PurchaseReturn({
    required this.returnId,
    required this.type,
    required this.state,
    required this.reason,
    required this.createdAt,
  });

  final int returnId;
  final String type;
  final String state;
  final String reason;
  final DateTime? createdAt;

  factory PurchaseReturn.fromJson(Map<String, dynamic> json) => PurchaseReturn(
    returnId: _requiredInt(json, 'id_devolucion'),
    type: _requiredString(json, 'tipo'),
    state: _requiredString(json, 'estado'),
    reason: _requiredString(json, 'motivo'),
    createdAt: _date(json['fecha']),
  );
}

class PurchaseBranch {
  const PurchaseBranch({required this.branchId, required this.name});

  final int branchId;
  final String name;

  factory PurchaseBranch.fromJson(Map<String, dynamic> json) => PurchaseBranch(
    branchId: _requiredInt(json, 'id_sucursal'),
    name: _requiredString(json, 'nombre'),
  );
}

class PurchasePayment {
  const PurchasePayment({
    required this.paymentId,
    required this.method,
    required this.state,
    required this.amount,
    required this.currency,
    required this.approvedDate,
  });

  final int paymentId;
  final String method;
  final String state;
  final double amount;
  final String currency;
  final DateTime? approvedDate;

  factory PurchasePayment.fromJson(Map<String, dynamic> json) => PurchasePayment(
    paymentId: _requiredInt(json, 'id_pago'),
    method: _requiredString(json, 'medio'),
    state: _requiredString(json, 'estado'),
    amount: _requiredDouble(json, 'monto'),
    currency: _requiredString(json, 'moneda'),
    approvedDate: _date(json['fecha_aprobacion']),
  );
}

class PurchaseItem {
  const PurchaseItem({
    required this.detailId,
    required this.variantId,
    required this.name,
    required this.size,
    required this.color,
    required this.quantity,
    required this.unitPrice,
    required this.unitDiscount,
    required this.lineSubtotal,
  });

  final int detailId;
  final int variantId;
  final String? name;
  final String? size;
  final String? color;
  final int quantity;
  final double unitPrice;
  final double unitDiscount;
  final double lineSubtotal;

  factory PurchaseItem.fromJson(Map<String, dynamic> json) => PurchaseItem(
    detailId: _requiredInt(json, 'id_detalle_venta'),
    variantId: _requiredInt(json, 'id_variante_producto'),
    name: _optionalString(json['nombre']),
    size: _optionalString(json['talla']),
    color: _optionalString(json['color']),
    quantity: _requiredInt(json, 'cantidad'),
    unitPrice: _requiredDouble(json, 'precio_unitario'),
    unitDiscount: _requiredDouble(json, 'descuento_unitario'),
    lineSubtotal: _requiredDouble(json, 'subtotal_linea'),
  );
}

enum PurchaseFailureType {
  unauthorized,
  forbidden,
  notFound,
  timeout,
  connection,
  invalidResponse,
  server,
}

class PurchaseFailure implements Exception {
  const PurchaseFailure(this.type, this.message);

  final PurchaseFailureType type;
  final String message;

  bool get invalidatesSession => type == PurchaseFailureType.unauthorized;
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

DateTime? _date(Object? value) {
  if (value == null) return null;
  if (value is! String) throw const FormatException('Fecha inválida.');
  return DateTime.tryParse(value);
}

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
