import '../catalog/catalog_models.dart';

enum ReservationState {
  pendiente('PENDIENTE'),
  confirmada('CONFIRMADA'),
  atendida('ATENDIDA'),
  cancelada('CANCELADA'),
  expirada('EXPIRADA');

  const ReservationState(this.apiValue);
  final String apiValue;

  String get label => '${apiValue[0]}${apiValue.substring(1).toLowerCase()}';

  static ReservationState parse(String value) => values.firstWhere(
    (state) => state.apiValue == value,
    orElse: () => throw const FormatException('Estado de reserva inválido.'),
  );
}

class ReservationBranch {
  const ReservationBranch({
    required this.id,
    required this.name,
    required this.address,
    required this.cityId,
    required this.cityName,
  });
  final int id;
  final String name;
  final String address;
  final int cityId;
  final String cityName;

  factory ReservationBranch.fromJson(Map<String, dynamic> json) {
    final city = _map(json, 'ciudad');
    return ReservationBranch(
      id: _int(json, 'id_sucursal'),
      name: _string(json, 'nombre'),
      address: _string(json, 'direccion'),
      cityId: _int(city, 'id_ciudad'),
      cityName: _string(city, 'nombre'),
    );
  }
}

class ReservationSummary {
  const ReservationSummary({
    required this.id,
    required this.code,
    required this.state,
    required this.createdAt,
    required this.scheduledAt,
    required this.expiresAt,
    required this.branch,
    required this.garmentCount,
    required this.total,
    required this.cancelable,
  });
  final int id;
  final String code;
  final ReservationState state;
  final DateTime createdAt;
  final DateTime scheduledAt;
  final DateTime expiresAt;
  final ReservationBranch branch;
  final int garmentCount;
  final double total;
  final bool cancelable;

  factory ReservationSummary.fromJson(Map<String, dynamic> json) =>
      ReservationSummary(
        id: _int(json, 'id_reserva'),
        code: _string(json, 'codigo'),
        state: ReservationState.parse(_string(json, 'estado')),
        createdAt: _date(json, 'created_at'),
        scheduledAt: _date(json, 'fecha_atencion_programada'),
        expiresAt: _date(json, 'fecha_expiracion'),
        branch: ReservationBranch.fromJson(_map(json, 'sucursal')),
        garmentCount: _int(json, 'cantidad_prendas'),
        total: _double(json, 'total'),
        cancelable: _bool(json, 'cancelable'),
      );
}

class ReservationItem {
  const ReservationItem({
    required this.variantId,
    required this.sku,
    required this.productId,
    required this.productName,
    required this.imageUrl,
    required this.size,
    required this.color,
    required this.quantity,
    required this.unitPrice,
    required this.subtotal,
  });
  final int variantId;
  final String sku;
  final int productId;
  final String productName;
  final String? imageUrl;
  final CatalogSize size;
  final CatalogColor color;
  final int quantity;
  final double unitPrice;
  final double subtotal;

  factory ReservationItem.fromJson(Map<String, dynamic> json) =>
      ReservationItem(
        variantId: _int(json, 'id_variante_producto'),
        sku: _string(json, 'sku'),
        productId: _int(json, 'id_producto'),
        productName: _string(json, 'producto'),
        imageUrl: _optionalString(json['imagen_principal']),
        size: CatalogSize.fromJson(_map(json, 'talla')),
        color: CatalogColor.fromJson(_map(json, 'color')),
        quantity: _int(json, 'cantidad'),
        unitPrice: _double(json, 'precio_unitario'),
        subtotal: _double(json, 'subtotal'),
      );
}

class ReservationDetail extends ReservationSummary {
  const ReservationDetail({
    required super.id,
    required super.code,
    required super.state,
    required super.createdAt,
    required super.scheduledAt,
    required super.expiresAt,
    required super.branch,
    required super.garmentCount,
    required super.total,
    required super.cancelable,
    required this.items,
  });
  final List<ReservationItem> items;

  factory ReservationDetail.fromJson(Map<String, dynamic> json) {
    final summary = ReservationSummary.fromJson(json);
    final rawItems = json['items'];
    if (rawItems is! List) throw const FormatException('Items inválidos.');
    return ReservationDetail(
      id: summary.id,
      code: summary.code,
      state: summary.state,
      createdAt: summary.createdAt,
      scheduledAt: summary.scheduledAt,
      expiresAt: summary.expiresAt,
      branch: summary.branch,
      garmentCount: summary.garmentCount,
      total: summary.total,
      cancelable: summary.cancelable,
      items: rawItems
          .map((item) {
            if (item is! Map<String, dynamic>) {
              throw const FormatException('Item inválido.');
            }
            return ReservationItem.fromJson(item);
          })
          .toList(growable: false),
    );
  }
}

class ReservationPagination {
  const ReservationPagination({
    required this.page,
    required this.pageSize,
    required this.total,
    required this.totalPages,
  });
  final int page;
  final int pageSize;
  final int total;
  final int totalPages;

  factory ReservationPagination.fromJson(Map<String, dynamic> json) =>
      ReservationPagination(
        page: _int(json, 'page'),
        pageSize: _int(json, 'page_size'),
        total: _int(json, 'total'),
        totalPages: _int(json, 'total_pages'),
      );
}

class ReservationPage {
  const ReservationPage({required this.data, required this.pagination});
  final List<ReservationSummary> data;
  final ReservationPagination pagination;
}

Map<String, dynamic> _map(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is! Map<String, dynamic>) throw FormatException('$key inválido.');
  return value;
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

bool _bool(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is bool) return value;
  throw FormatException('$key inválido.');
}

DateTime _date(Map<String, dynamic> json, String key) {
  final value = _string(json, key);
  final hasZone =
      value.endsWith('Z') || RegExp(r'[+-]\d{2}:\d{2}$').hasMatch(value);
  final parsed = DateTime.tryParse(hasZone ? value : '${value}Z');
  if (parsed == null) throw FormatException('$key inválido.');
  return parsed.toUtc();
}
