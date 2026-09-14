enum CatalogSection {
  hombre('HOMBRE', 'Hombre'),
  mujer('MUJER', 'Mujer'),
  unisex('UNISEX', 'Unisex');

  const CatalogSection(this.apiValue, this.label);
  final String apiValue;
  final String label;

  static CatalogSection parse(String value) => values.firstWhere(
    (item) => item.apiValue == value,
    orElse: () => throw const FormatException('Sección inválida.'),
  );
}

enum CatalogSort {
  recientes('recientes', 'Más recientes'),
  precioAsc('precio_asc', 'Precio: menor a mayor'),
  precioDesc('precio_desc', 'Precio: mayor a menor'),
  nombre('nombre', 'Nombre');

  const CatalogSort(this.apiValue, this.label);
  final String apiValue;
  final String label;
}

class CatalogColor {
  const CatalogColor({
    required this.id,
    required this.name,
    required this.hexCode,
  });
  final int id;
  final String name;
  final String? hexCode;

  factory CatalogColor.fromJson(Map<String, dynamic> json) => CatalogColor(
    id: _requiredInt(json, 'id_color'),
    name: _requiredString(json, 'nombre'),
    hexCode: _optionalString(json['codigo_hex']),
  );
}

class CatalogSize {
  const CatalogSize({required this.id, required this.name});
  final int id;
  final String name;

  factory CatalogSize.fromJson(Map<String, dynamic> json) => CatalogSize(
    id: _requiredInt(json, 'id_talla'),
    name: _requiredString(json, 'nombre'),
  );
}

class CatalogCollection {
  const CatalogCollection({required this.id, required this.name});
  final int id;
  final String name;

  factory CatalogCollection.fromJson(Map<String, dynamic> json) =>
      CatalogCollection(
        id: _requiredInt(json, 'id_coleccion'),
        name: _requiredString(json, 'nombre'),
      );
}

class CatalogImageData {
  const CatalogImageData({
    required this.id,
    required this.url,
    required this.isPrimary,
  });
  final int id;
  final String url;
  final bool isPrimary;

  factory CatalogImageData.fromJson(Map<String, dynamic> json) =>
      CatalogImageData(
        id: _requiredInt(json, 'id_imagen_producto'),
        url: _requiredString(json, 'url_imagen'),
        isPrimary: _requiredBool(json, 'es_principal'),
      );
}

class CatalogPromotion {
  const CatalogPromotion({
    required this.id,
    required this.name,
    required this.code,
    required this.description,
    required this.discountType,
    required this.value,
    required this.discountPercentage,
    required this.discountAmount,
    required this.resultPrice,
    required this.startDate,
    required this.endDate,
    required this.stackable,
  });
  final int id;
  final String name;
  final String? code;
  final String? description;
  final String discountType;
  final double value;
  final double? discountPercentage;
  final double discountAmount;
  final double resultPrice;
  final DateTime startDate;
  final DateTime endDate;
  final bool stackable;

  factory CatalogPromotion.fromJson(Map<String, dynamic> json) =>
      CatalogPromotion(
        id: _requiredInt(json, 'id_promocion'),
        name: _requiredString(json, 'nombre'),
        code: _optionalString(json['codigo']),
        description: _optionalString(json['descripcion']),
        discountType: _requiredString(json, 'tipo_descuento'),
        value: _requiredDouble(json, 'valor'),
        discountPercentage: _optionalDouble(json['porcentaje_descuento']),
        discountAmount: _requiredDouble(json, 'monto_descuento'),
        resultPrice: _requiredDouble(json, 'precio_resultante'),
        startDate: _requiredDate(json, 'fecha_inicio'),
        endDate: _requiredDate(json, 'fecha_fin'),
        stackable: _requiredBool(json, 'acumulable'),
      );
}

class CatalogProductAvailability {
  const CatalogProductAvailability({
    required this.branchId,
    required this.branch,
    required this.status,
    required this.availableQuantity,
  });
  final int branchId;
  final String branch;
  final String status;
  final int availableQuantity;

  factory CatalogProductAvailability.fromJson(Map<String, dynamic> json) =>
      CatalogProductAvailability(
        branchId: _requiredInt(json, 'id_sucursal'),
        branch: _requiredString(json, 'sucursal'),
        status: _requiredString(json, 'estado'),
        availableQuantity: _requiredInt(json, 'cantidad_disponible'),
      );
}

class CatalogProduct {
  const CatalogProduct({
    required this.id,
    required this.name,
    required this.shortDescription,
    required this.section,
    required this.categoryId,
    required this.category,
    required this.basePrice,
    required this.finalPrice,
    required this.hasPromotion,
    required this.highlightedPromotion,
    required this.discountPercentage,
    required this.discountAmount,
    required this.primaryImage,
    required this.availableColors,
    required this.availableSizes,
    required this.branchAvailability,
  });
  final int id;
  final String name;
  final String? shortDescription;
  final CatalogSection section;
  final int categoryId;
  final String category;
  final double basePrice;
  final double finalPrice;
  final bool hasPromotion;
  final CatalogPromotion? highlightedPromotion;
  final double? discountPercentage;
  final double? discountAmount;
  final String? primaryImage;
  final List<CatalogColor> availableColors;
  final List<CatalogSize> availableSizes;
  final CatalogProductAvailability? branchAvailability;

  factory CatalogProduct.fromJson(Map<String, dynamic> json) => CatalogProduct(
    id: _requiredInt(json, 'id_producto'),
    name: _requiredString(json, 'nombre'),
    shortDescription: _optionalString(json['descripcion_corta']),
    section: CatalogSection.parse(_requiredString(json, 'seccion')),
    categoryId: _requiredInt(json, 'id_categoria'),
    category: _requiredString(json, 'categoria'),
    basePrice: _requiredDouble(json, 'precio_base'),
    finalPrice: _requiredDouble(json, 'precio_final'),
    hasPromotion: _requiredBool(json, 'tiene_promocion'),
    highlightedPromotion: _optionalObject(
      json['promocion_destacada'],
      CatalogPromotion.fromJson,
    ),
    discountPercentage: _optionalDouble(json['porcentaje_descuento']),
    discountAmount: _optionalDouble(json['monto_descuento']),
    primaryImage: _optionalString(json['imagen_principal']),
    availableColors: _requiredList(
      json,
      'colores_disponibles',
      CatalogColor.fromJson,
    ),
    availableSizes: _requiredList(
      json,
      'tallas_disponibles',
      CatalogSize.fromJson,
    ),
    branchAvailability: _optionalObject(
      json['disponibilidad_sucursal'],
      CatalogProductAvailability.fromJson,
    ),
  );
}

class CatalogVariantAvailability {
  const CatalogVariantAvailability({
    required this.branchId,
    required this.status,
    required this.availableQuantity,
  });
  final int branchId;
  final String status;
  final int availableQuantity;

  factory CatalogVariantAvailability.fromJson(Map<String, dynamic> json) =>
      CatalogVariantAvailability(
        branchId: _requiredInt(json, 'id_sucursal'),
        status: _requiredString(json, 'estado'),
        availableQuantity: _requiredInt(json, 'cantidad_disponible'),
      );
}

class CatalogVariant {
  const CatalogVariant({
    required this.id,
    required this.sku,
    required this.size,
    required this.color,
    required this.branchAvailability,
  });
  final int id;
  final String sku;
  final CatalogSize size;
  final CatalogColor color;
  final CatalogVariantAvailability? branchAvailability;

  factory CatalogVariant.fromJson(Map<String, dynamic> json) => CatalogVariant(
    id: _requiredInt(json, 'id_variante_producto'),
    sku: _requiredString(json, 'sku'),
    size: _requiredObject(json, 'talla', CatalogSize.fromJson),
    color: _requiredObject(json, 'color', CatalogColor.fromJson),
    branchAvailability: _optionalObject(
      json['disponibilidad_sucursal'],
      CatalogVariantAvailability.fromJson,
    ),
  );
}

class CatalogProductDetail {
  const CatalogProductDetail({
    required this.id,
    required this.name,
    required this.description,
    required this.section,
    required this.categoryId,
    required this.category,
    required this.seasonId,
    required this.season,
    required this.basePrice,
    required this.finalPrice,
    required this.hasPromotion,
    required this.promotions,
    required this.highlightedPromotion,
    required this.discountPercentage,
    required this.discountAmount,
    required this.primaryImage,
    required this.gallery,
    required this.variants,
    required this.sizes,
    required this.colors,
    required this.collections,
  });
  final int id;
  final String name;
  final String? description;
  final CatalogSection section;
  final int categoryId;
  final String category;
  final int? seasonId;
  final String? season;
  final double basePrice;
  final double finalPrice;
  final bool hasPromotion;
  final List<CatalogPromotion> promotions;
  final CatalogPromotion? highlightedPromotion;
  final double? discountPercentage;
  final double? discountAmount;
  final String? primaryImage;
  final List<CatalogImageData> gallery;
  final List<CatalogVariant> variants;
  final List<CatalogSize> sizes;
  final List<CatalogColor> colors;
  final List<CatalogCollection> collections;

  List<String> get imageUrls {
    final urls = <String>[];
    if (primaryImage != null && primaryImage!.trim().isNotEmpty) {
      urls.add(primaryImage!.trim());
    }
    for (final image in gallery) {
      if (!urls.contains(image.url)) urls.add(image.url);
    }
    return urls;
  }

  factory CatalogProductDetail.fromJson(Map<String, dynamic> json) =>
      CatalogProductDetail(
        id: _requiredInt(json, 'id_producto'),
        name: _requiredString(json, 'nombre'),
        description: _optionalString(json['descripcion']),
        section: CatalogSection.parse(_requiredString(json, 'seccion')),
        categoryId: _requiredInt(json, 'id_categoria'),
        category: _requiredString(json, 'categoria'),
        seasonId: _optionalInt(json['id_temporada']),
        season: _optionalString(json['temporada']),
        basePrice: _requiredDouble(json, 'precio_base'),
        finalPrice: _requiredDouble(json, 'precio_final'),
        hasPromotion: _requiredBool(json, 'tiene_promocion'),
        promotions: _requiredList(
          json,
          'promociones_vigentes',
          CatalogPromotion.fromJson,
        ),
        highlightedPromotion: _optionalObject(
          json['promocion_destacada'],
          CatalogPromotion.fromJson,
        ),
        discountPercentage: _optionalDouble(json['porcentaje_descuento']),
        discountAmount: _optionalDouble(json['monto_descuento']),
        primaryImage: _optionalString(json['imagen_principal']),
        gallery: _requiredList(json, 'galeria', CatalogImageData.fromJson),
        variants: _requiredList(json, 'variantes', CatalogVariant.fromJson),
        sizes: _requiredList(json, 'tallas', CatalogSize.fromJson),
        colors: _requiredList(json, 'colores', CatalogColor.fromJson),
        collections: _requiredList(
          json,
          'colecciones',
          CatalogCollection.fromJson,
        ),
      );
}

class CatalogPagination {
  const CatalogPagination({
    required this.page,
    required this.pageSize,
    required this.total,
    required this.totalPages,
  });
  final int page;
  final int pageSize;
  final int total;
  final int totalPages;

  factory CatalogPagination.fromJson(Map<String, dynamic> json) =>
      CatalogPagination(
        page: _requiredInt(json, 'page'),
        pageSize: _requiredInt(json, 'page_size'),
        total: _requiredInt(json, 'total'),
        totalPages: _requiredInt(json, 'total_pages'),
      );
}

class CatalogPage {
  const CatalogPage({required this.products, required this.pagination});
  final List<CatalogProduct> products;
  final CatalogPagination pagination;
}

class CatalogFilters {
  const CatalogFilters({
    this.search,
    this.section,
    this.categoryId,
    this.sizeId,
    this.colorId,
    this.minimumPrice,
    this.maximumPrice,
    this.onPromotion,
    this.sort = CatalogSort.recientes,
    this.page = 1,
    this.pageSize = 12,
  });
  final String? search;
  final CatalogSection? section;
  final int? categoryId;
  final int? sizeId;
  final int? colorId;
  final double? minimumPrice;
  final double? maximumPrice;
  final bool? onPromotion;
  final CatalogSort sort;
  final int page;
  final int pageSize;

  Map<String, String> toQueryParameters() => {
    'page': '$page',
    'page_size': '$pageSize',
    'sort': sort.apiValue,
    if (search != null && search!.trim().isNotEmpty) 'search': search!.trim(),
    if (section != null) 'seccion': section!.apiValue,
    if (categoryId != null) 'id_categoria': '$categoryId',
    if (sizeId != null) 'id_talla': '$sizeId',
    if (colorId != null) 'id_color': '$colorId',
    if (minimumPrice != null) 'precio_min': _queryNumber(minimumPrice!),
    if (maximumPrice != null) 'precio_max': _queryNumber(maximumPrice!),
    if (onPromotion != null) 'en_promocion': '$onPromotion',
  };
}

T _requiredObject<T>(
  Map<String, dynamic> json,
  String key,
  T Function(Map<String, dynamic>) parser,
) {
  final value = json[key];
  if (value is! Map<String, dynamic>) {
    throw FormatException('$key inválido.');
  }
  return parser(value);
}

T? _optionalObject<T>(Object? value, T Function(Map<String, dynamic>) parser) {
  if (value == null) return null;
  if (value is! Map<String, dynamic>) {
    throw const FormatException('Objeto opcional inválido.');
  }
  return parser(value);
}

List<T> _requiredList<T>(
  Map<String, dynamic> json,
  String key,
  T Function(Map<String, dynamic>) parser,
) {
  final value = json[key];
  if (value is! List) throw FormatException('$key inválido.');
  return value
      .map((item) {
        if (item is! Map<String, dynamic>) {
          throw FormatException('$key contiene un elemento inválido.');
        }
        return parser(item);
      })
      .toList(growable: false);
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
  final normalized = value.trim();
  return normalized.isEmpty ? null : normalized;
}

int _requiredInt(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is! int) throw FormatException('$key inválido.');
  return value;
}

int? _optionalInt(Object? value) {
  if (value == null) return null;
  if (value is! int) throw const FormatException('Entero inválido.');
  return value;
}

bool _requiredBool(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is! bool) throw FormatException('$key inválido.');
  return value;
}

double _requiredDouble(Map<String, dynamic> json, String key) {
  final value = _optionalDouble(json[key]);
  if (value == null) throw FormatException('$key inválido.');
  return value;
}

double? _optionalDouble(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toDouble();
  if (value is String) return double.tryParse(value);
  throw const FormatException('Decimal inválido.');
}

DateTime _requiredDate(Map<String, dynamic> json, String key) {
  final value = json[key];
  final parsed = value is String ? DateTime.tryParse(value) : null;
  if (parsed == null) throw FormatException('$key inválido.');
  return parsed;
}

String _queryNumber(double value) => value == value.roundToDouble()
    ? value.toInt().toString()
    : value.toString();
