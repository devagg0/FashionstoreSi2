import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';
import '../../auth/widgets/auth_components.dart';
import '../availability_models.dart';
import '../availability_service.dart';
import '../catalog_models.dart';
import 'catalog_widgets.dart';

class ProductAvailabilityPanel extends StatefulWidget {
  const ProductAvailabilityPanel({
    super.key,
    required this.productId,
    required this.variants,
    required this.sizes,
    required this.colors,
    this.availabilityGateway,
    this.onSelectionChanged,
  });

  final int productId;
  final List<CatalogVariant> variants;
  final List<CatalogSize> sizes;
  final List<CatalogColor> colors;
  final CatalogAvailabilityGateway? availabilityGateway;
  final ValueChanged<VariantAvailabilitySelection?>? onSelectionChanged;

  @override
  State<ProductAvailabilityPanel> createState() =>
      _ProductAvailabilityPanelState();
}

class _ProductAvailabilityPanelState extends State<ProductAvailabilityPanel> {
  late final CatalogAvailabilityGateway _gateway;
  late final bool _ownsService;

  int? _sizeId;
  int? _colorId;
  List<BranchAvailability> _branches = const [];
  String? _errorMessage;
  bool _loading = false;
  bool _combinationUnavailable = false;
  int _requestSequence = 0;

  @override
  void initState() {
    super.initState();
    _ownsService = widget.availabilityGateway == null;
    _gateway = widget.availabilityGateway ?? CatalogAvailabilityService();
  }

  @override
  void dispose() {
    if (_ownsService && _gateway is CatalogAvailabilityService) {
      _gateway.close();
    }
    super.dispose();
  }

  void _selectSize(int id) {
    if (_sizeId == id) return;
    setState(() => _sizeId = id);
    _updateAvailability();
  }

  void _selectColor(int id) {
    if (_colorId == id) return;
    setState(() => _colorId = id);
    _updateAvailability();
  }

  Future<void> _updateAvailability() async {
    final sequence = ++_requestSequence;
    widget.onSelectionChanged?.call(null);
    if (_sizeId == null || _colorId == null) {
      setState(() {
        _branches = const [];
        _errorMessage = null;
        _loading = false;
        _combinationUnavailable = false;
      });
      return;
    }

    CatalogVariant? variant;
    for (final candidate in widget.variants) {
      if (candidate.size.id == _sizeId && candidate.color.id == _colorId) {
        variant = candidate;
        break;
      }
    }
    if (variant == null) {
      setState(() {
        _branches = const [];
        _errorMessage = null;
        _loading = false;
        _combinationUnavailable = true;
      });
      return;
    }

    setState(() {
      _branches = const [];
      _errorMessage = null;
      _loading = true;
      _combinationUnavailable = false;
    });
    try {
      final result = await _gateway.loadVariantAvailability(
        productId: widget.productId,
        variantId: variant.id,
      );
      if (!mounted || sequence != _requestSequence) return;
      setState(() {
        _branches = result.branches
            .where((branch) => branch.variantId == variant!.id)
            .toList(growable: false);
      });
      widget.onSelectionChanged?.call(
        VariantAvailabilitySelection(variant: variant, branches: _branches),
      );
    } on AvailabilityFailure catch (error) {
      if (mounted && sequence == _requestSequence) {
        setState(() => _errorMessage = error.message);
      }
    } catch (_) {
      if (mounted && sequence == _requestSequence) {
        setState(
          () => _errorMessage = 'No pudimos consultar la disponibilidad.',
        );
      }
    } finally {
      if (mounted && sequence == _requestSequence) {
        setState(() => _loading = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) => Column(
    key: const Key('productAvailabilityPanel'),
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      const Text(
        'Disponibilidad por sucursal',
        style: TextStyle(
          color: AppColors.espresso,
          fontSize: 19,
          fontWeight: FontWeight.w800,
        ),
      ),
      const SizedBox(height: 6),
      const Text(
        'Selecciona talla y color para consultar el stock disponible.',
        style: TextStyle(color: AppColors.muted, height: 1.4),
      ),
      const SizedBox(height: 18),
      _selector(
        title: 'Talla',
        children: widget.sizes.map(
          (size) => ChoiceChip(
            key: Key('availabilitySize-${size.id}'),
            label: Text(size.name),
            selected: _sizeId == size.id,
            onSelected: (_) => _selectSize(size.id),
          ),
        ),
      ),
      const SizedBox(height: 15),
      _selector(
        title: 'Color',
        children: widget.colors.map(
          (color) => ChoiceChip(
            key: Key('availabilityColor-${color.id}'),
            avatar: CircleAvatar(
              backgroundColor: catalogSwatchColor(color.hexCode),
            ),
            label: Text(color.name),
            selected: _colorId == color.id,
            onSelected: (_) => _selectColor(color.id),
          ),
        ),
      ),
      const SizedBox(height: 20),
      _availabilityContent(),
    ],
  );

  Widget _selector({
    required String title,
    required Iterable<Widget> children,
  }) {
    final options = children.toList(growable: false);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: const TextStyle(
            color: AppColors.espresso,
            fontWeight: FontWeight.w700,
          ),
        ),
        const SizedBox(height: 8),
        if (options.isEmpty)
          const Text(
            'Sin opciones disponibles',
            style: TextStyle(color: AppColors.muted),
          )
        else
          Wrap(spacing: 8, runSpacing: 8, children: options),
      ],
    );
  }

  Widget _availabilityContent() {
    if (_sizeId == null || _colorId == null) {
      return const _AvailabilityMessage(
        key: Key('availabilitySelectionPrompt'),
        icon: Icons.touch_app_outlined,
        message: 'Selecciona una talla y un color.',
      );
    }
    if (_combinationUnavailable) {
      return const _AvailabilityMessage(
        key: Key('availabilityEmpty'),
        icon: Icons.inventory_2_outlined,
        message: 'Sin disponibilidad',
      );
    }
    if (_loading) return const _AvailabilitySkeleton();
    if (_errorMessage != null) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          AuthStatusBanner(message: _errorMessage!),
          const SizedBox(height: 10),
          OutlinedButton.icon(
            key: const Key('retryAvailabilityButton'),
            onPressed: _updateAvailability,
            icon: const Icon(Icons.refresh_rounded),
            label: const Text('Reintentar'),
          ),
        ],
      );
    }
    if (_branches.isEmpty) {
      return const _AvailabilityMessage(
        key: Key('availabilityEmpty'),
        icon: Icons.inventory_2_outlined,
        message: 'Sin disponibilidad',
      );
    }
    return Column(
      key: const Key('availabilityBranchList'),
      children: _branches.map(_branchCard).toList(growable: false),
    );
  }

  Widget _branchCard(BranchAvailability branch) => Container(
    key: Key('availabilityBranch-${branch.branchId}'),
    width: double.infinity,
    margin: const EdgeInsets.only(bottom: 10),
    padding: const EdgeInsets.all(15),
    decoration: BoxDecoration(
      color: AppColors.white,
      border: Border.all(color: AppColors.line),
      borderRadius: BorderRadius.circular(12),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            const Icon(Icons.storefront_outlined, color: AppColors.terracotta),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    branch.branchName,
                    style: const TextStyle(
                      color: AppColors.espresso,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                  Text(
                    branch.cityName,
                    style: const TextStyle(
                      color: AppColors.muted,
                      fontSize: 12,
                    ),
                  ),
                ],
              ),
            ),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
              decoration: BoxDecoration(
                color: branch.availableStock > 0
                    ? const Color(0xFFE7F3EA)
                    : const Color(0xFFF4E8E4),
                borderRadius: BorderRadius.circular(20),
              ),
              child: Text(
                branch.availableStock > 0
                    ? 'Stock: ${branch.availableStock}'
                    : 'Sin disponibilidad',
                style: TextStyle(
                  color: branch.availableStock > 0
                      ? AppColors.success
                      : AppColors.error,
                  fontSize: 11,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        Text(
          '${branch.color.name} · Talla ${branch.size.name}',
          style: const TextStyle(color: AppColors.espresso),
        ),
        const SizedBox(height: 3),
        Text(
          'SKU ${branch.sku}',
          style: const TextStyle(color: AppColors.muted, fontSize: 12),
        ),
      ],
    ),
  );
}

class _AvailabilityMessage extends StatelessWidget {
  const _AvailabilityMessage({
    super.key,
    required this.icon,
    required this.message,
  });
  final IconData icon;
  final String message;

  @override
  Widget build(BuildContext context) => Container(
    width: double.infinity,
    padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 24),
    decoration: BoxDecoration(
      color: AppColors.white,
      border: Border.all(color: AppColors.line),
      borderRadius: BorderRadius.circular(12),
    ),
    child: Column(
      children: [
        Icon(icon, color: AppColors.terracotta),
        const SizedBox(height: 8),
        Text(
          message,
          textAlign: TextAlign.center,
          style: const TextStyle(color: AppColors.muted),
        ),
      ],
    ),
  );
}

class _AvailabilitySkeleton extends StatelessWidget {
  const _AvailabilitySkeleton();

  @override
  Widget build(BuildContext context) => Column(
    key: const Key('availabilityLoading'),
    children: List.generate(
      2,
      (index) => Container(
        height: 104,
        margin: const EdgeInsets.only(bottom: 10),
        decoration: BoxDecoration(
          color: AppColors.line,
          borderRadius: BorderRadius.circular(12),
        ),
      ),
    ),
  );
}
