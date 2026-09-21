import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../auth/widgets/auth_components.dart';
import '../reservations/reservation_draft.dart';
import '../reservations/widgets/reservation_action_panel.dart';
import 'availability_models.dart';
import 'availability_service.dart';
import 'catalog_models.dart';
import 'catalog_service.dart';
import 'widgets/catalog_widgets.dart';
import 'widgets/product_availability_panel.dart';

class ProductDetailScreen extends StatefulWidget {
  const ProductDetailScreen({
    super.key,
    required this.productId,
    this.catalogGateway,
    this.availabilityGateway,
    this.reservationDraft,
    this.onOpenReservationDraft,
    this.onAddToCart,
  });

  final int productId;
  final CatalogGateway? catalogGateway;
  final CatalogAvailabilityGateway? availabilityGateway;
  final ReservationDraftController? reservationDraft;
  final VoidCallback? onOpenReservationDraft;
  final Future<void> Function(int variantId, int quantity)? onAddToCart;

  @override
  State<ProductDetailScreen> createState() => _ProductDetailScreenState();
}

class _ProductDetailScreenState extends State<ProductDetailScreen> {
  late final CatalogGateway _gateway;
  late final bool _ownsService;
  final _pageController = PageController();

  CatalogProductDetail? _product;
  String? _errorMessage;
  bool _loading = true;
  int _imageIndex = 0;
  VariantAvailabilitySelection? _availabilitySelection;

  @override
  void initState() {
    super.initState();
    _ownsService = widget.catalogGateway == null;
    _gateway = widget.catalogGateway ?? CatalogService();
    _load();
  }

  @override
  void dispose() {
    _pageController.dispose();
    if (_ownsService && _gateway is CatalogService) _gateway.close();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _errorMessage = null;
    });
    try {
      final product = await _gateway.loadProductDetail(widget.productId);
      if (!mounted) {
        return;
      }
      setState(() {
        _product = product;
        _imageIndex = 0;
      });
    } on CatalogFailure catch (error) {
      if (mounted) {
        setState(() => _errorMessage = error.message);
      }
    } catch (_) {
      if (mounted) {
        setState(() => _errorMessage = 'No pudimos cargar esta prenda.');
      }
    } finally {
      if (mounted) {
        setState(() => _loading = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final horizontalPadding = MediaQuery.sizeOf(context).width < 370
        ? 16.0
        : 22.0;
    return Scaffold(
      body: SafeArea(
        child: CustomScrollView(
          key: const Key('productDetailScrollView'),
          slivers: [
            SliverAppBar(
              pinned: true,
              backgroundColor: AppColors.linen,
              surfaceTintColor: AppColors.linen,
              leading: IconButton(
                key: const Key('productDetailBackButton'),
                tooltip: 'Volver al catálogo',
                onPressed: () => Navigator.of(context).pop(),
                icon: const Icon(Icons.arrow_back_rounded),
              ),
              title: const Text(
                'DETALLE DE PRENDA',
                style: TextStyle(
                  color: AppColors.espresso,
                  fontSize: 12,
                  fontWeight: FontWeight.w800,
                  letterSpacing: 1.7,
                ),
              ),
            ),
            SliverPadding(
              padding: EdgeInsets.fromLTRB(
                horizontalPadding,
                18,
                horizontalPadding,
                36,
              ),
              sliver: SliverToBoxAdapter(
                child: Center(
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 760),
                    child: AnimatedSwitcher(
                      duration: const Duration(milliseconds: 220),
                      child: _content(context),
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _content(BuildContext context) {
    if (_loading) return const _DetailSkeleton(key: ValueKey('detailLoading'));
    if (_errorMessage != null) {
      return Column(
        key: const ValueKey('detailError'),
        children: [
          AuthStatusBanner(message: _errorMessage!),
          const SizedBox(height: 18),
          FilledButton.icon(
            key: const Key('retryProductDetailButton'),
            onPressed: _load,
            icon: const Icon(Icons.refresh_rounded),
            label: const Text('Reintentar'),
          ),
        ],
      );
    }
    final product = _product!;
    return Column(
      key: const ValueKey('detailContent'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _gallery(product),
        const SizedBox(height: 26),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            _MetaPill(product.category),
            _MetaPill(product.section.label),
            if (product.season != null)
              _MetaPill('Temporada ${product.season}'),
          ],
        ),
        const SizedBox(height: 14),
        Text(
          product.name,
          key: const Key('productDetailName'),
          style: Theme.of(context).textTheme.headlineMedium?.copyWith(
            color: AppColors.espresso,
            fontSize: 30,
            fontWeight: FontWeight.w800,
          ),
        ),
        const SizedBox(height: 12),
        _PriceBlock(
          basePrice: product.basePrice,
          finalPrice: product.finalPrice,
          promotion: product.highlightedPromotion,
        ),
        const SizedBox(height: 22),
        Text(
          product.description ??
              'Esta prenda no tiene una descripción disponible.',
          style: const TextStyle(
            color: AppColors.muted,
            fontSize: 15,
            height: 1.55,
          ),
        ),
        const SizedBox(height: 28),
        ProductAvailabilityPanel(
          productId: product.id,
          variants: product.variants,
          sizes: product.sizes,
          colors: product.colors,
          availabilityGateway: widget.availabilityGateway,
          onSelectionChanged: (selection) {
            if (mounted) setState(() => _availabilitySelection = selection);
          },
        ),
        if (_availabilitySelection != null && widget.onAddToCart != null) ...[
          const SizedBox(height: 18),
          FilledButton.icon(
            key: const Key('addToCartFromDetailButton'),
            onPressed: () async {
              await widget.onAddToCart!(_availabilitySelection!.variant.id, 1);
            },
            icon: const Icon(Icons.add_shopping_cart_rounded),
            label: const Text('Agregar al carrito'),
          ),
        ],
        if (_availabilitySelection != null &&
            widget.reservationDraft != null &&
            widget.onOpenReservationDraft != null) ...[
          const SizedBox(height: 18),
          ReservationActionPanel(
            product: product,
            selection: _availabilitySelection!,
            draft: widget.reservationDraft!,
            onOpenDraft: widget.onOpenReservationDraft!,
          ),
        ],
        const SizedBox(height: 25),
        _sectionTitle('Variantes activas'),
        const SizedBox(height: 11),
        if (product.variants.isEmpty)
          const Text(
            'Sin variantes disponibles',
            style: TextStyle(color: AppColors.muted),
          )
        else
          ...product.variants.map(_variantTile),
        if (product.collections.isNotEmpty) ...[
          const SizedBox(height: 25),
          _sectionTitle('Colecciones'),
          const SizedBox(height: 11),
          _chipsOrEmpty(product.collections.map((item) => item.name)),
        ],
        if (product.promotions.length > 1) ...[
          const SizedBox(height: 25),
          _sectionTitle('Promociones vigentes'),
          const SizedBox(height: 11),
          ...product.promotions.map(
            (promotion) => Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Text(
                '• ${promotion.name} · ${formatCatalogMoney(promotion.resultPrice)}',
                style: const TextStyle(color: AppColors.muted),
              ),
            ),
          ),
        ],
      ],
    );
  }

  Widget _gallery(CatalogProductDetail product) {
    final images = product.imageUrls;
    if (images.isEmpty) {
      return const AspectRatio(
        aspectRatio: 0.9,
        child: ClipRRect(
          borderRadius: BorderRadius.all(Radius.circular(16)),
          child: CatalogImageFallback(),
        ),
      );
    }
    return Column(
      children: [
        AspectRatio(
          aspectRatio: 0.9,
          child: ClipRRect(
            borderRadius: BorderRadius.circular(16),
            child: PageView.builder(
              key: const Key('productGallery'),
              controller: _pageController,
              itemCount: images.length,
              onPageChanged: (index) => setState(() => _imageIndex = index),
              itemBuilder: (_, index) => CatalogImageView(
                imageUrl: images[index],
                semanticLabel: product.name,
              ),
            ),
          ),
        ),
        if (images.length > 1) ...[
          const SizedBox(height: 10),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: List.generate(
              images.length,
              (index) => Container(
                width: index == _imageIndex ? 20 : 7,
                height: 7,
                margin: const EdgeInsets.symmetric(horizontal: 3),
                decoration: BoxDecoration(
                  color: index == _imageIndex
                      ? AppColors.terracotta
                      : AppColors.line,
                  borderRadius: BorderRadius.circular(8),
                ),
              ),
            ),
          ),
        ],
      ],
    );
  }

  Widget _variantTile(CatalogVariant variant) {
    final availability = variant.branchAvailability;
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 9),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.white,
        border: Border.all(color: AppColors.line),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '${variant.color.name} · Talla ${variant.size.name}',
                  style: const TextStyle(
                    color: AppColors.espresso,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 3),
                Text(
                  variant.sku,
                  style: const TextStyle(color: AppColors.muted, fontSize: 12),
                ),
              ],
            ),
          ),
          if (availability != null)
            Text(
              availability.status,
              style: TextStyle(
                color: availability.status == 'DISPONIBLE'
                    ? AppColors.success
                    : AppColors.error,
                fontSize: 11,
                fontWeight: FontWeight.w800,
              ),
            ),
        ],
      ),
    );
  }

  Widget _chipsOrEmpty(Iterable<String> labels) {
    final values = labels.toList();
    if (values.isEmpty) {
      return const Text(
        'Sin opciones disponibles',
        style: TextStyle(color: AppColors.muted),
      );
    }
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: values
          .map(
            (label) => Chip(
              label: Text(label),
              backgroundColor: AppColors.white,
              side: const BorderSide(color: AppColors.line),
            ),
          )
          .toList(),
    );
  }

  Widget _sectionTitle(String value) => Text(
    value,
    style: const TextStyle(
      color: AppColors.espresso,
      fontSize: 17,
      fontWeight: FontWeight.w800,
    ),
  );
}

class _MetaPill extends StatelessWidget {
  const _MetaPill(this.label);
  final String label;
  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
    decoration: BoxDecoration(
      color: AppColors.white,
      border: Border.all(color: AppColors.line),
      borderRadius: BorderRadius.circular(20),
    ),
    child: Text(
      label,
      style: const TextStyle(
        color: AppColors.muted,
        fontSize: 11,
        fontWeight: FontWeight.w700,
      ),
    ),
  );
}

class _PriceBlock extends StatelessWidget {
  const _PriceBlock({
    required this.basePrice,
    required this.finalPrice,
    required this.promotion,
  });
  final double basePrice;
  final double finalPrice;
  final CatalogPromotion? promotion;

  @override
  Widget build(BuildContext context) => Wrap(
    spacing: 11,
    runSpacing: 7,
    crossAxisAlignment: WrapCrossAlignment.center,
    children: [
      if (promotion != null)
        Text(
          formatCatalogMoney(basePrice),
          style: const TextStyle(
            color: AppColors.muted,
            fontSize: 15,
            decoration: TextDecoration.lineThrough,
          ),
        ),
      Text(
        formatCatalogMoney(finalPrice),
        style: const TextStyle(
          color: AppColors.espresso,
          fontSize: 24,
          fontWeight: FontWeight.w800,
        ),
      ),
      if (promotion != null)
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
          decoration: BoxDecoration(
            color: AppColors.terracotta,
            borderRadius: BorderRadius.circular(20),
          ),
          child: Text(
            promotion!.name,
            style: const TextStyle(
              color: AppColors.white,
              fontSize: 11,
              fontWeight: FontWeight.w800,
            ),
          ),
        ),
    ],
  );
}

class _DetailSkeleton extends StatelessWidget {
  const _DetailSkeleton({super.key});
  @override
  Widget build(BuildContext context) => Column(
    key: const Key('productDetailLoading'),
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Container(
        height: 370,
        decoration: BoxDecoration(
          color: AppColors.line,
          borderRadius: BorderRadius.circular(16),
        ),
      ),
      const SizedBox(height: 24),
      for (final width in [170.0, 260.0, 210.0]) ...[
        Container(
          width: width,
          height: 18,
          margin: const EdgeInsets.only(bottom: 12),
          decoration: BoxDecoration(
            color: AppColors.line,
            borderRadius: BorderRadius.circular(8),
          ),
        ),
      ],
    ],
  );
}
