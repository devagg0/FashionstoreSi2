import 'package:mobile/features/catalog/catalog_models.dart';

CatalogPromotion catalogPromotion() => CatalogPromotion(
  id: 7,
  name: 'Oferta de temporada',
  code: null,
  description: 'Promoción vigente',
  discountType: 'PORCENTAJE',
  value: 20,
  discountPercentage: 20,
  discountAmount: 20,
  resultPrice: 80,
  startDate: DateTime(2026, 1, 1),
  endDate: DateTime(2026, 12, 31),
  stackable: false,
);

CatalogProduct catalogProduct({
  String? image,
  bool promotion = true,
  CatalogSection section = CatalogSection.unisex,
}) => CatalogProduct(
  id: 10,
  name: 'Chaqueta urbana',
  shortDescription: 'Chaqueta ligera',
  section: section,
  categoryId: 3,
  category: 'Chaquetas',
  basePrice: 100,
  finalPrice: promotion ? 80 : 100,
  hasPromotion: promotion,
  highlightedPromotion: promotion ? catalogPromotion() : null,
  discountPercentage: promotion ? 20 : null,
  discountAmount: promotion ? 20 : null,
  primaryImage: image,
  availableColors: const [
    CatalogColor(id: 4, name: 'Negro', hexCode: '#111111'),
  ],
  availableSizes: const [CatalogSize(id: 2, name: 'M')],
  branchAvailability: null,
);

CatalogProductDetail catalogDetail({List<CatalogImageData>? gallery}) =>
    CatalogProductDetail(
      id: 10,
      name: 'Chaqueta urbana',
      description: 'Una prenda versátil para todos los días.',
      section: CatalogSection.unisex,
      categoryId: 3,
      category: 'Chaquetas',
      seasonId: 2,
      season: 'Invierno',
      basePrice: 100,
      finalPrice: 80,
      hasPromotion: true,
      promotions: [catalogPromotion()],
      highlightedPromotion: catalogPromotion(),
      discountPercentage: 20,
      discountAmount: 20,
      primaryImage: null,
      gallery: gallery ?? const [],
      variants: const [
        CatalogVariant(
          id: 90,
          sku: 'CHA-NEG-M',
          size: CatalogSize(id: 2, name: 'M'),
          color: CatalogColor(id: 4, name: 'Negro', hexCode: '#111111'),
          branchAvailability: null,
        ),
      ],
      sizes: const [CatalogSize(id: 2, name: 'M')],
      colors: const [CatalogColor(id: 4, name: 'Negro', hexCode: '#111111')],
      collections: const [CatalogCollection(id: 5, name: 'Esenciales')],
    );

CatalogPage catalogPage({List<CatalogProduct>? products}) => CatalogPage(
  products: products ?? [catalogProduct()],
  pagination: CatalogPagination(
    page: 1,
    pageSize: 12,
    total: products?.length ?? 1,
    totalPages: 1,
  ),
);
