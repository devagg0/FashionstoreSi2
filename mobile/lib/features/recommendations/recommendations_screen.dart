import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../auth/widgets/auth_components.dart';
import '../catalog/product_detail_screen.dart';
import '../catalog/widgets/catalog_widgets.dart';
import 'recommendation_models.dart';
import 'recommendation_service.dart';

class RecommendationsScreen extends StatefulWidget {
  const RecommendationsScreen({
    super.key,
    this.recommendationGateway,
    required this.onBack,
    this.onSessionInvalidated,
  });

  final RecommendationGateway? recommendationGateway;
  final VoidCallback onBack;
  final Future<void> Function(String message)? onSessionInvalidated;

  @override
  State<RecommendationsScreen> createState() => _RecommendationsScreenState();
}

class _RecommendationsScreenState extends State<RecommendationsScreen> {
  late final RecommendationGateway _gateway;
  late final bool _ownsService;
  List<RecommendationItem> _items = const [];
  String _origin = 'FALLBACK';
  String? _errorMessage;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _ownsService = widget.recommendationGateway == null;
    _gateway = widget.recommendationGateway ?? RecommendationService();
    _load();
  }

  @override
  void dispose() {
    if (_ownsService && _gateway is RecommendationService) _gateway.close();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() { _loading = true; _errorMessage = null; });
    try {
      final page = await _gateway.loadRecommendations();
      if (!mounted) return;
      setState(() { _items = page.items; _origin = page.origin; });
    } on RecommendationFailure catch (error) {
      if (!mounted) return;
      if (error.invalidatesSession && widget.onSessionInvalidated != null) {
        await widget.onSessionInvalidated!(error.message);
      } else {
        setState(() => _errorMessage = error.message);
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final padding = MediaQuery.sizeOf(context).width < 370 ? 18.0 : 22.0;
    return Scaffold(
      body: SafeArea(
        child: CustomScrollView(
          slivers: [
            SliverAppBar(
              pinned: true,
              backgroundColor: AppColors.linen,
              surfaceTintColor: AppColors.linen,
              leading: IconButton(
                key: const Key('recommendationsBackButton'),
                tooltip: 'Volver',
                onPressed: widget.onBack,
                icon: const Icon(Icons.arrow_back_rounded),
              ),
              title: const Text('RECOMENDACIONES'),
            ),
            SliverPadding(
              padding: EdgeInsets.fromLTRB(padding, 18, padding, 32),
              sliver: SliverToBoxAdapter(
                child: Center(
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 720),
                    child: _content(),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _content() {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_errorMessage != null) {
      return Column(
        children: [
          AuthStatusBanner(message: _errorMessage!),
          const SizedBox(height: 18),
          FilledButton.icon(
            key: const Key('retryRecommendationsButton'),
            onPressed: _load,
            icon: const Icon(Icons.refresh_rounded),
            label: const Text('Reintentar'),
          ),
        ],
      );
    }
    if (_items.isEmpty) {
      return const Text('Todavía no encontramos prendas recomendadas para ti.', textAlign: TextAlign.center);
    }
    return Column(
      key: const ValueKey('recommendationsContent'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          _origin == 'PERSONALIZADO' ? 'Elegidas para ti' : 'Descubre estas prendas',
          style: const TextStyle(color: AppColors.espresso, fontSize: 24, fontWeight: FontWeight.w800),
        ),
        const SizedBox(height: 6),
        Text(
          _origin == 'PERSONALIZADO' ? 'Basadas en tus compras, reservas y carrito.' : 'Una selección disponible del catálogo.',
          style: const TextStyle(color: AppColors.muted),
        ),
        const SizedBox(height: 18),
        ..._items.map(_recommendationCard),
      ],
    );
  }

  Widget _recommendationCard(RecommendationItem item) => InkWell(
    key: Key('recommendationCard-${item.productId}'),
    borderRadius: BorderRadius.circular(14),
    onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(
      builder: (_) => ProductDetailScreen(productId: item.productId),
    )),
    child: Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 14),
      decoration: BoxDecoration(color: AppColors.white, borderRadius: BorderRadius.circular(14), border: Border.all(color: AppColors.line)),
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            height: 190,
            width: double.infinity,
            child: CatalogImageView(imageUrl: item.primaryImage, semanticLabel: item.name),
          ),
          Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(child: Text(item.name, maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(color: AppColors.espresso, fontSize: 18, fontWeight: FontWeight.w800))),
                    const SizedBox(width: 10),
                    Flexible(child: Text(formatCatalogMoney(item.finalPrice), textAlign: TextAlign.right, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(color: AppColors.terracotta, fontWeight: FontWeight.w800))),
                  ],
                ),
                const SizedBox(height: 8),
                Text('${item.category} · ${item.section.label}', maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(color: AppColors.muted, fontWeight: FontWeight.w600)),
                if (item.suggestedVariant != null) ...[
                  const SizedBox(height: 8),
                  Text('Talla ${item.suggestedVariant!.size} · ${item.suggestedVariant!.color}', maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(color: AppColors.muted)),
                  const SizedBox(height: 4),
                  Text(_stockLabel(item.suggestedVariant!.availableStock), style: const TextStyle(color: AppColors.terracotta, fontWeight: FontWeight.w700)),
                ],
                const SizedBox(height: 8),
                Text(item.reason, maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(color: AppColors.muted, fontSize: 13)),
              ],
            ),
          ),
        ],
      ),
    ),
  );

  String _stockLabel(int stock) {
    if (stock <= 0) return 'Sin disponibilidad';
    if (stock <= 5) return 'Últimas $stock unidades';
    return 'Disponible';
  }
}
