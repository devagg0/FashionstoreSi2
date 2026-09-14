import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';
import '../catalog_models.dart';

String formatCatalogMoney(double value) => 'Bs ${value.toStringAsFixed(2)}';

class CatalogImageView extends StatelessWidget {
  const CatalogImageView({
    super.key,
    required this.imageUrl,
    this.fit = BoxFit.cover,
    this.semanticLabel,
  });

  final String? imageUrl;
  final BoxFit fit;
  final String? semanticLabel;

  @override
  Widget build(BuildContext context) {
    final url = imageUrl?.trim();
    if (url == null || url.isEmpty) return const CatalogImageFallback();
    return Image.network(
      url,
      fit: fit,
      semanticLabel: semanticLabel,
      loadingBuilder: (context, child, progress) {
        if (progress == null) return child;
        return const ColoredBox(
          color: AppColors.linen,
          child: Center(
            child: SizedBox.square(
              dimension: 22,
              child: CircularProgressIndicator(strokeWidth: 2),
            ),
          ),
        );
      },
      errorBuilder: (_, _, _) => const CatalogImageFallback(),
    );
  }
}

class CatalogImageFallback extends StatelessWidget {
  const CatalogImageFallback({super.key});

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      key: const Key('catalogImageFallback'),
      color: const Color(0xFFECE3DA),
      child: LayoutBuilder(
        builder: (context, constraints) {
          final compact =
              constraints.maxHeight < 90 || constraints.maxWidth < 90;
          return Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  'FS',
                  style: TextStyle(
                    color: AppColors.terracotta,
                    fontSize: compact ? 17 : 25,
                    fontWeight: FontWeight.w800,
                    letterSpacing: compact ? 1 : 2,
                  ),
                ),
                if (!compact) ...[
                  const SizedBox(height: 5),
                  const Text(
                    'Imagen no disponible',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: AppColors.muted, fontSize: 10),
                  ),
                ],
              ],
            ),
          );
        },
      ),
    );
  }
}

class CatalogProductCard extends StatelessWidget {
  const CatalogProductCard({
    super.key,
    required this.product,
    required this.onTap,
  });

  final CatalogProduct product;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      key: Key('catalogProduct-${product.id}'),
      color: AppColors.white,
      borderRadius: BorderRadius.circular(14),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: Stack(
                fit: StackFit.expand,
                children: [
                  CatalogImageView(
                    imageUrl: product.primaryImage,
                    semanticLabel: product.name,
                  ),
                  if (product.hasPromotion)
                    Positioned(
                      left: 10,
                      top: 10,
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 9,
                          vertical: 5,
                        ),
                        decoration: BoxDecoration(
                          color: AppColors.terracotta,
                          borderRadius: BorderRadius.circular(20),
                        ),
                        child: Text(
                          _promotionLabel(product),
                          style: const TextStyle(
                            color: AppColors.white,
                            fontSize: 10,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                      ),
                    ),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 12, 12, 14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${product.category} · ${product.section.label}',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: AppColors.terracotta,
                      fontSize: 9.5,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 0.4,
                    ),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    product.name,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: AppColors.espresso,
                      fontSize: 14,
                      height: 1.2,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 8),
                  if (product.hasPromotion)
                    Text(
                      formatCatalogMoney(product.basePrice),
                      style: const TextStyle(
                        color: AppColors.muted,
                        fontSize: 11,
                        decoration: TextDecoration.lineThrough,
                      ),
                    ),
                  Text(
                    formatCatalogMoney(product.finalPrice),
                    style: const TextStyle(
                      color: AppColors.espresso,
                      fontSize: 15,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  String _promotionLabel(CatalogProduct product) {
    final percentage = product.discountPercentage;
    if (percentage != null) return '-${percentage.round()}%';
    return product.highlightedPromotion?.name ?? 'OFERTA';
  }
}

Color catalogSwatchColor(String? code) {
  final normalized = code?.replaceFirst('#', '').trim();
  if (normalized == null ||
      (normalized.length != 6 && normalized.length != 8)) {
    return AppColors.clay;
  }
  final parsed = int.tryParse(normalized, radix: 16);
  if (parsed == null) return AppColors.clay;
  return Color(normalized.length == 6 ? 0xFF000000 | parsed : parsed);
}
