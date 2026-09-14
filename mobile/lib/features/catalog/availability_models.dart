import 'catalog_models.dart';

class BranchAvailability {
  const BranchAvailability({
    required this.variantId,
    required this.sku,
    required this.size,
    required this.color,
    required this.branchId,
    required this.branchName,
    required this.cityId,
    required this.cityName,
    required this.address,
    required this.openingTime,
    required this.closingTime,
    required this.availableStock,
  });

  final int variantId;
  final String sku;
  final CatalogSize size;
  final CatalogColor color;
  final int branchId;
  final String branchName;
  final int cityId;
  final String cityName;
  final String address;
  final String? openingTime;
  final String? closingTime;
  final int availableStock;

  factory BranchAvailability.fromJson(Map<String, dynamic> json) {
    final variant = _requiredMap(json, 'variante');
    final availableStock = _requiredInt(json, 'stock_disponible');
    if (availableStock < 0) {
      throw const FormatException('stock_disponible inválido.');
    }
    return BranchAvailability(
      variantId: _requiredInt(variant, 'id_variante_producto'),
      sku: _requiredString(variant, 'sku'),
      size: CatalogSize.fromJson(_requiredMap(variant, 'talla')),
      color: CatalogColor.fromJson(_requiredMap(variant, 'color')),
      branchId: _requiredInt(json, 'id_sucursal'),
      branchName: _requiredString(json, 'nombre_sucursal'),
      cityId: _requiredInt(json, 'id_ciudad'),
      cityName: _requiredString(json, 'nombre_ciudad'),
      address: _requiredString(json, 'direccion'),
      openingTime: _optionalString(json['hora_apertura']),
      closingTime: _optionalString(json['hora_cierre']),
      availableStock: availableStock,
    );
  }
}

String? _optionalString(Object? value) {
  if (value == null) return null;
  if (value is! String || value.trim().isEmpty) {
    throw const FormatException('Texto opcional inválido.');
  }
  return value.trim();
}

class CatalogAvailabilityResult {
  const CatalogAvailabilityResult({
    required this.productId,
    required this.productName,
    required this.branches,
  });

  final int productId;
  final String productName;
  final List<BranchAvailability> branches;

  factory CatalogAvailabilityResult.fromJson(Map<String, dynamic> json) {
    final product = _requiredMap(json, 'producto');
    final availability = json['disponibilidad'];
    if (availability is! List) {
      throw const FormatException('Disponibilidad inválida.');
    }
    return CatalogAvailabilityResult(
      productId: _requiredInt(product, 'id_producto'),
      productName: _requiredString(product, 'nombre'),
      branches: availability
          .map((item) {
            if (item is! Map<String, dynamic>) {
              throw const FormatException('Sucursal inválida.');
            }
            return BranchAvailability.fromJson(item);
          })
          .toList(growable: false),
    );
  }
}

class VariantAvailabilitySelection {
  const VariantAvailabilitySelection({
    required this.variant,
    required this.branches,
  });
  final CatalogVariant variant;
  final List<BranchAvailability> branches;
}

Map<String, dynamic> _requiredMap(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is! Map<String, dynamic>) {
    throw FormatException('$key inválido.');
  }
  return value;
}

int _requiredInt(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is int) return value;
  if (value is num && value == value.roundToDouble()) return value.toInt();
  throw FormatException('$key inválido.');
}

String _requiredString(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is! String || value.trim().isEmpty) {
    throw FormatException('$key inválido.');
  }
  return value.trim();
}
