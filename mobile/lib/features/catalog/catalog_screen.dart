import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../auth/widgets/auth_components.dart';
import '../reservations/reservation_draft.dart';
import 'catalog_models.dart';
import 'catalog_service.dart';
import 'product_detail_screen.dart';
import 'widgets/catalog_widgets.dart';

class CatalogScreen extends StatefulWidget {
  const CatalogScreen({
    super.key,
    this.catalogGateway,
    required this.onBack,
    this.reservationDraft,
    this.onOpenReservationDraft,
    this.onAddToCart,
    this.onOpenCart,
  });

  final CatalogGateway? catalogGateway;
  final VoidCallback onBack;
  final ReservationDraftController? reservationDraft;
  final VoidCallback? onOpenReservationDraft;
  final Future<void> Function(int variantId, int quantity)? onAddToCart;
  final VoidCallback? onOpenCart;

  @override
  State<CatalogScreen> createState() => _CatalogScreenState();
}

class _CatalogScreenState extends State<CatalogScreen> {
  final _searchController = TextEditingController();
  final _minimumPriceController = TextEditingController();
  final _maximumPriceController = TextEditingController();

  late final CatalogGateway _gateway;
  late final bool _ownsService;

  final Map<int, String> _categories = {};
  final Map<int, CatalogSize> _sizes = {};
  final Map<int, CatalogColor> _colors = {};
  final List<CatalogProduct> _products = [];
  final Set<CatalogSection> _availableSections = {};

  CatalogSection? _section;
  int? _categoryId;
  int? _sizeId;
  int? _colorId;
  bool _onlyPromotions = false;
  CatalogSort _sort = CatalogSort.recientes;
  bool _filtersVisible = false;
  bool _loadingSections = true;
  bool _loading = false;
  bool _loadingMore = false;
  String? _sectionErrorMessage;
  String? _errorMessage;
  String? _filterError;
  int _page = 1;
  int _total = 0;
  int _totalPages = 0;
  int _requestSequence = 0;

  @override
  void initState() {
    super.initState();
    _ownsService = widget.catalogGateway == null;
    _gateway = widget.catalogGateway ?? CatalogService();
    _loadSections();
  }

  Future<void> _loadSections() async {
    setState(() {
      _loadingSections = true;
      _sectionErrorMessage = null;
    });
    try {
      final results = await Future.wait(
        CatalogSection.values.map(
          (section) async => (
            section,
            await _gateway.loadProducts(
              CatalogFilters(section: section, page: 1, pageSize: 1),
            ),
          ),
        ),
      );
      if (!mounted) {
        return;
      }
      setState(() {
        _availableSections
          ..clear()
          ..addAll(
            results
                .where(
                  (result) => result.$2.products.any(
                    (product) => product.section == result.$1,
                  ),
                )
                .map((result) => result.$1),
          );
      });
    } on CatalogFailure catch (error) {
      if (mounted) {
        setState(() => _sectionErrorMessage = error.message);
      }
    } catch (_) {
      if (mounted) {
        setState(
          () => _sectionErrorMessage =
              'No pudimos consultar las secciones disponibles.',
        );
      }
    } finally {
      if (mounted) {
        setState(() => _loadingSections = false);
      }
    }
  }

  void _selectSection(CatalogSection section) {
    if (_section == section) {
      return;
    }
    FocusManager.instance.primaryFocus?.unfocus();
    setState(() {
      _section = section;
      _categoryId = null;
      _sizeId = null;
      _colorId = null;
      _filterError = null;
      _filtersVisible = false;
      _categories.clear();
      _sizes.clear();
      _colors.clear();
      _products.clear();
      _total = 0;
      _totalPages = 0;
      _page = 1;
    });
    _loadProducts(reset: true);
  }

  @override
  void dispose() {
    _searchController.dispose();
    _minimumPriceController.dispose();
    _maximumPriceController.dispose();
    if (_ownsService && _gateway is CatalogService) _gateway.close();
    super.dispose();
  }

  Future<void> _loadProducts({required bool reset}) async {
    if (_loadingMore || (!reset && _page >= _totalPages)) return;
    final nextPage = reset ? 1 : _page + 1;
    final sequence = ++_requestSequence;
    setState(() {
      if (reset) {
        _loading = true;
        _errorMessage = null;
      } else {
        _loadingMore = true;
      }
    });

    try {
      final page = await _gateway.loadProducts(_filters(page: nextPage));
      if (!mounted || sequence != _requestSequence) return;
      setState(() {
        if (reset) _products.clear();
        _products.addAll(page.products);
        _page = page.pagination.page;
        _total = page.pagination.total;
        _totalPages = page.pagination.totalPages;
        _mergeOptions(page.products);
      });
    } on CatalogFailure catch (error) {
      if (mounted && sequence == _requestSequence) {
        setState(() => _errorMessage = error.message);
      }
    } catch (_) {
      if (mounted && sequence == _requestSequence) {
        setState(() => _errorMessage = 'No pudimos cargar el catálogo.');
      }
    } finally {
      if (mounted && sequence == _requestSequence) {
        setState(() {
          _loading = false;
          _loadingMore = false;
        });
      }
    }
  }

  CatalogFilters _filters({required int page}) => CatalogFilters(
    search: _searchController.text.trim(),
    section: _section,
    categoryId: _categoryId,
    sizeId: _sizeId,
    colorId: _colorId,
    minimumPrice: _parsePrice(_minimumPriceController.text),
    maximumPrice: _parsePrice(_maximumPriceController.text),
    onPromotion: _onlyPromotions ? true : null,
    sort: _sort,
    page: page,
    pageSize: 12,
  );

  void _mergeOptions(List<CatalogProduct> products) {
    for (final product in products) {
      _categories[product.categoryId] = product.category;
      for (final size in product.availableSizes) {
        _sizes[size.id] = size;
      }
      for (final color in product.availableColors) {
        _colors[color.id] = color;
      }
    }
  }

  void _applyFilters() {
    final minimum = _validatePrice(
      _minimumPriceController.text,
      label: 'precio mínimo',
    );
    final maximum = _validatePrice(
      _maximumPriceController.text,
      label: 'precio máximo',
    );
    if (minimum.$2 != null || maximum.$2 != null) {
      setState(() => _filterError = minimum.$2 ?? maximum.$2);
      return;
    }
    if (minimum.$1 != null && maximum.$1 != null && minimum.$1! > maximum.$1!) {
      setState(
        () => _filterError =
            'El precio mínimo no puede ser mayor que el precio máximo.',
      );
      return;
    }
    FocusManager.instance.primaryFocus?.unfocus();
    setState(() {
      _filterError = null;
      _filtersVisible = false;
    });
    _loadProducts(reset: true);
  }

  void _clearFilters() {
    _searchController.clear();
    _minimumPriceController.clear();
    _maximumPriceController.clear();
    setState(() {
      _categoryId = null;
      _sizeId = null;
      _colorId = null;
      _onlyPromotions = false;
      _filterError = null;
      _filtersVisible = false;
    });
    _loadProducts(reset: true);
  }

  (double?, String?) _validatePrice(String value, {required String label}) {
    final normalized = value.trim();
    if (normalized.isEmpty) return (null, null);
    final parsed = double.tryParse(normalized.replaceFirst(',', '.'));
    if (parsed == null || !parsed.isFinite || parsed < 0) {
      return (null, 'Ingresa un $label válido.');
    }
    return (parsed, null);
  }

  double? _parsePrice(String value) =>
      _validatePrice(value, label: 'precio').$1;

  int get _activeFilterCount => [
    if (_searchController.text.trim().isNotEmpty) true,
    _categoryId,
    _sizeId,
    _colorId,
    if (_minimumPriceController.text.trim().isNotEmpty) true,
    if (_maximumPriceController.text.trim().isNotEmpty) true,
    if (_onlyPromotions) true,
  ].length;

  Future<void> _openDetail(CatalogProduct product) =>
      Navigator.of(context).push(
        MaterialPageRoute<void>(
          builder: (detailContext) => ProductDetailScreen(
            productId: product.id,
            catalogGateway: _gateway,
            reservationDraft: widget.reservationDraft,
            onOpenReservationDraft: widget.onOpenReservationDraft == null
                ? null
                : () {
                    Navigator.of(detailContext).pop();
                    widget.onOpenReservationDraft!();
                  },
            onAddToCart: widget.onAddToCart == null
                ? null
                : (variantId, quantity) async {
                    await widget.onAddToCart!(variantId, quantity);
                  if (!detailContext.mounted) return;
                    Navigator.of(detailContext).pop();
                    if (widget.onOpenCart != null) {
                      widget.onOpenCart!();
                    }
                  },
          ),
        ),
      );

  @override
  Widget build(BuildContext context) {
    final width = MediaQuery.sizeOf(context).width;
    final horizontalPadding = width < 370 ? 14.0 : 20.0;
    return Scaffold(
      body: SafeArea(
        child: CustomScrollView(
          key: const Key('catalogScrollView'),
          keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
          slivers: [
            SliverAppBar(
              pinned: true,
              backgroundColor: AppColors.linen,
              surfaceTintColor: AppColors.linen,
              leading: IconButton(
                key: const Key('catalogBackButton'),
                tooltip: 'Volver al inicio',
                onPressed: widget.onBack,
                icon: const Icon(Icons.arrow_back_rounded),
              ),
              title: const Text(
                'FASHIONSTORE',
                style: TextStyle(
                  color: AppColors.espresso,
                  fontSize: 13,
                  fontWeight: FontWeight.w800,
                  letterSpacing: 2.1,
                ),
              ),
              actions: [
                if (widget.onOpenCart != null)
                  IconButton(
                    key: const Key('catalogOpenCartButton'),
                    tooltip: 'Mi carrito',
                    onPressed: widget.onOpenCart,
                    icon: const Icon(Icons.shopping_cart_outlined),
                  ),
              ],
            ),
            SliverPadding(
              padding: EdgeInsets.fromLTRB(
                horizontalPadding,
                18,
                horizontalPadding,
                16,
              ),
              sliver: SliverToBoxAdapter(child: _hero(context)),
            ),
            SliverPadding(
              padding: EdgeInsets.symmetric(horizontal: horizontalPadding),
              sliver: SliverToBoxAdapter(child: _sectionSelector()),
            ),
            if (_section != null) ...[
              SliverPadding(
                padding: EdgeInsets.fromLTRB(
                  horizontalPadding,
                  18,
                  horizontalPadding,
                  0,
                ),
                sliver: SliverToBoxAdapter(child: _toolbar()),
              ),
              if (_filtersVisible)
                SliverPadding(
                  padding: EdgeInsets.fromLTRB(
                    horizontalPadding,
                    14,
                    horizontalPadding,
                    4,
                  ),
                  sliver: SliverToBoxAdapter(child: _filterPanel()),
                ),
              SliverPadding(
                padding: EdgeInsets.fromLTRB(
                  horizontalPadding,
                  18,
                  horizontalPadding,
                  8,
                ),
                sliver: SliverToBoxAdapter(child: _resultHeading()),
              ),
              ..._resultSlivers(horizontalPadding),
            ] else
              ..._sectionEntrySlivers(horizontalPadding),
            const SliverToBoxAdapter(child: SizedBox(height: 34)),
          ],
        ),
      ),
    );
  }

  Widget _hero(BuildContext context) => Container(
    padding: const EdgeInsets.all(22),
    decoration: BoxDecoration(
      gradient: const LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [AppColors.clay, AppColors.terracotta],
      ),
      borderRadius: BorderRadius.circular(18),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'COLECCIÓN FASHIONSTORE',
          style: TextStyle(
            color: AppColors.espresso,
            fontSize: 10,
            fontWeight: FontWeight.w800,
            letterSpacing: 1.8,
          ),
        ),
        const SizedBox(height: 8),
        Text(
          'Encuentra tu próxima prenda',
          style: Theme.of(context).textTheme.headlineSmall?.copyWith(
            color: AppColors.espresso,
            fontWeight: FontWeight.w800,
          ),
        ),
        const SizedBox(height: 7),
        Text(
          _section == null
              ? 'Elige una sección para comenzar'
              : _loading
              ? 'Preparando la selección...'
              : '$_total prendas en ${_section!.label}',
          style: const TextStyle(color: AppColors.espresso, fontSize: 13),
        ),
      ],
    ),
  );

  Widget _sectionSelector() {
    if (_loadingSections) {
      return Row(
        key: const Key('catalogSectionLoading'),
        children: List.generate(
          3,
          (index) => Expanded(
            child: Container(
              height: 104,
              margin: EdgeInsets.only(right: index == 2 ? 0 : 8),
              decoration: BoxDecoration(
                color: AppColors.line,
                borderRadius: BorderRadius.circular(14),
              ),
            ),
          ),
        ),
      );
    }
    if (_sectionErrorMessage != null || _availableSections.isEmpty) {
      return const SizedBox.shrink();
    }
    final sections = CatalogSection.values
        .where(_availableSections.contains)
        .toList(growable: false);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          _section == null ? 'Compra por sección' : 'Cambiar de sección',
          style: const TextStyle(
            color: AppColors.espresso,
            fontSize: 20,
            fontWeight: FontWeight.w800,
          ),
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            for (var index = 0; index < sections.length; index++) ...[
              Expanded(
                child: _SectionCard(
                  section: sections[index],
                  selected: _section == sections[index],
                  onTap: () => _selectSection(sections[index]),
                ),
              ),
              if (index < sections.length - 1) const SizedBox(width: 8),
            ],
          ],
        ),
      ],
    );
  }

  List<Widget> _sectionEntrySlivers(double horizontalPadding) {
    if (_loadingSections) {
      return const [];
    }
    if (_sectionErrorMessage != null) {
      return [
        SliverPadding(
          padding: EdgeInsets.all(horizontalPadding),
          sliver: SliverToBoxAdapter(
            child: Column(
              children: [
                AuthStatusBanner(message: _sectionErrorMessage!),
                const SizedBox(height: 16),
                FilledButton.icon(
                  key: const Key('retryCatalogSectionsButton'),
                  onPressed: _loadSections,
                  icon: const Icon(Icons.refresh_rounded),
                  label: const Text('Reintentar'),
                ),
              ],
            ),
          ),
        ),
      ];
    }
    if (_availableSections.isEmpty) {
      return const [
        SliverPadding(
          padding: EdgeInsets.all(24),
          sliver: SliverToBoxAdapter(
            child: Text(
              'No hay secciones con prendas disponibles en este momento.',
              key: Key('emptyCatalogSections'),
              textAlign: TextAlign.center,
              style: TextStyle(color: AppColors.muted),
            ),
          ),
        ),
      ];
    }
    return const [
      SliverPadding(
        padding: EdgeInsets.fromLTRB(24, 24, 24, 0),
        sliver: SliverToBoxAdapter(
          child: Text(
            'Selecciona Hombre, Mujer o Unisex para ver las prendas de esa sección.',
            key: Key('catalogSectionPrompt'),
            textAlign: TextAlign.center,
            style: TextStyle(color: AppColors.muted, height: 1.45),
          ),
        ),
      ),
    ];
  }

  Widget _toolbar() => Column(
    children: [
      TextField(
        key: const Key('catalogSearchField'),
        controller: _searchController,
        textInputAction: TextInputAction.search,
        decoration: InputDecoration(
          hintText: 'Buscar por nombre o SKU',
          prefixIcon: const Icon(Icons.search_rounded),
          suffixIcon: IconButton(
            key: const Key('catalogSearchButton'),
            tooltip: 'Buscar',
            onPressed: _applyFilters,
            icon: const Icon(Icons.arrow_forward_rounded),
          ),
        ),
        onSubmitted: (_) => _applyFilters(),
      ),
      const SizedBox(height: 12),
      Row(
        children: [
          Expanded(
            child: OutlinedButton.icon(
              key: const Key('toggleCatalogFiltersButton'),
              onPressed: () =>
                  setState(() => _filtersVisible = !_filtersVisible),
              icon: const Icon(Icons.tune_rounded),
              label: Text(
                _activeFilterCount == 0
                    ? 'Filtros'
                    : 'Filtros ($_activeFilterCount)',
              ),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: DropdownButtonFormField<CatalogSort>(
              key: ValueKey('catalogSort-${_sort.apiValue}'),
              initialValue: _sort,
              isExpanded: true,
              decoration: const InputDecoration(
                contentPadding: EdgeInsets.symmetric(horizontal: 12),
              ),
              items: CatalogSort.values
                  .map(
                    (sort) => DropdownMenuItem(
                      value: sort,
                      child: Text(
                        sort.label,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontSize: 12),
                      ),
                    ),
                  )
                  .toList(),
              onChanged: (sort) {
                if (sort == null || sort == _sort) return;
                setState(() => _sort = sort);
                _loadProducts(reset: true);
              },
            ),
          ),
        ],
      ),
    ],
  );

  Widget _filterPanel() {
    final categories = _categories.entries.toList()
      ..sort((a, b) => a.value.compareTo(b.value));
    final sizes = _sizes.values.toList()
      ..sort((a, b) => a.name.compareTo(b.name));
    final colors = _colors.values.toList()
      ..sort((a, b) => a.name.compareTo(b.name));
    return Material(
      key: const Key('catalogFilterPanel'),
      color: AppColors.white,
      shape: RoundedRectangleBorder(
        side: const BorderSide(color: AppColors.line),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text(
              'Refina tu selección',
              style: TextStyle(
                color: AppColors.espresso,
                fontSize: 17,
                fontWeight: FontWeight.w800,
              ),
            ),
            const SizedBox(height: 16),
            _idDropdown(
              key: const Key('catalogCategoryFilter'),
              label: 'Categoría',
              allLabel: 'Todas las categorías',
              value: _categoryId,
              options: {for (final item in categories) item.key: item.value},
              onChanged: (value) => setState(() => _categoryId = value),
            ),
            const SizedBox(height: 12),
            _idDropdown(
              key: const Key('catalogSizeFilter'),
              label: 'Talla',
              allLabel: 'Todas las tallas',
              value: _sizeId,
              options: {for (final item in sizes) item.id: item.name},
              onChanged: (value) => setState(() => _sizeId = value),
            ),
            const SizedBox(height: 12),
            _idDropdown(
              key: const Key('catalogColorFilter'),
              label: 'Color',
              allLabel: 'Todos los colores',
              value: _colorId,
              options: {for (final item in colors) item.id: item.name},
              onChanged: (value) => setState(() => _colorId = value),
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: TextField(
                    key: const Key('catalogMinimumPriceFilter'),
                    controller: _minimumPriceController,
                    keyboardType: const TextInputType.numberWithOptions(
                      decimal: true,
                    ),
                    decoration: const InputDecoration(
                      labelText: 'Precio desde',
                      hintText: 'Bs 0',
                    ),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: TextField(
                    key: const Key('catalogMaximumPriceFilter'),
                    controller: _maximumPriceController,
                    keyboardType: const TextInputType.numberWithOptions(
                      decimal: true,
                    ),
                    decoration: const InputDecoration(
                      labelText: 'Precio hasta',
                      hintText: 'Sin límite',
                    ),
                  ),
                ),
              ],
            ),
            SwitchListTile.adaptive(
              key: const Key('catalogPromotionFilter'),
              contentPadding: EdgeInsets.zero,
              title: const Text('Solo productos en oferta'),
              value: _onlyPromotions,
              activeTrackColor: AppColors.terracotta,
              onChanged: (value) => setState(() => _onlyPromotions = value),
            ),
            if (_filterError != null) ...[
              AuthStatusBanner(message: _filterError!),
              const SizedBox(height: 12),
            ],
            FilledButton(
              key: const Key('applyCatalogFiltersButton'),
              onPressed: _applyFilters,
              child: const Text('Ver resultados'),
            ),
            TextButton(
              key: const Key('clearCatalogFiltersButton'),
              onPressed: _clearFilters,
              child: const Text('Limpiar filtros'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _idDropdown({
    required Key key,
    required String label,
    required String allLabel,
    required int? value,
    required Map<int, String> options,
    required ValueChanged<int?> onChanged,
  }) => KeyedSubtree(
    key: ValueKey('catalogDropdown-$label-${value ?? 0}-${options.length}'),
    child: DropdownButtonFormField<int>(
      key: key,
      initialValue: value ?? 0,
      isExpanded: true,
      decoration: InputDecoration(labelText: label),
      items: [
        DropdownMenuItem(value: 0, child: Text(allLabel)),
        ...options.entries.map(
          (item) => DropdownMenuItem(value: item.key, child: Text(item.value)),
        ),
      ],
      onChanged: (selected) => onChanged(selected == 0 ? null : selected),
    ),
  );

  Widget _resultHeading() => Row(
    children: [
      Expanded(
        child: Text(
          _products.isEmpty ? 'Todos los productos' : 'Nuestra selección',
          style: const TextStyle(
            color: AppColors.espresso,
            fontSize: 20,
            fontWeight: FontWeight.w800,
          ),
        ),
      ),
      if (!_loading && _total > 0)
        Text(
          '$_total total',
          style: const TextStyle(color: AppColors.muted, fontSize: 12),
        ),
    ],
  );

  List<Widget> _resultSlivers(double horizontalPadding) {
    if (_loading) return [_skeletonGrid(horizontalPadding)];
    if (_errorMessage != null) {
      return [
        SliverPadding(
          padding: EdgeInsets.all(horizontalPadding),
          sliver: SliverToBoxAdapter(
            child: Column(
              children: [
                AuthStatusBanner(message: _errorMessage!),
                const SizedBox(height: 16),
                FilledButton.icon(
                  key: const Key('retryCatalogButton'),
                  onPressed: () => _loadProducts(reset: true),
                  icon: const Icon(Icons.refresh_rounded),
                  label: const Text('Intentar nuevamente'),
                ),
              ],
            ),
          ),
        ),
      ];
    }
    if (_products.isEmpty) {
      return [
        SliverPadding(
          padding: EdgeInsets.all(horizontalPadding),
          sliver: SliverToBoxAdapter(
            child: Container(
              key: const Key('emptyCatalogState'),
              padding: const EdgeInsets.symmetric(vertical: 42, horizontal: 20),
              child: Column(
                children: [
                  const Icon(
                    Icons.search_off_rounded,
                    color: AppColors.terracotta,
                    size: 38,
                  ),
                  const SizedBox(height: 13),
                  const Text(
                    'No encontramos prendas',
                    style: TextStyle(
                      color: AppColors.espresso,
                      fontSize: 20,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                  const SizedBox(height: 7),
                  const Text(
                    'Prueba otra búsqueda o limpia algunos filtros.',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: AppColors.muted),
                  ),
                  TextButton(
                    onPressed: _clearFilters,
                    child: const Text('Limpiar filtros'),
                  ),
                ],
              ),
            ),
          ),
        ),
      ];
    }
    return [
      SliverPadding(
        padding: EdgeInsets.symmetric(horizontal: horizontalPadding),
        sliver: SliverGrid(
          delegate: SliverChildBuilderDelegate(
            (context, index) => CatalogProductCard(
              product: _products[index],
              onTap: () => _openDetail(_products[index]),
            ),
            childCount: _products.length,
          ),
          gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
            maxCrossAxisExtent: 255,
            mainAxisExtent: 335,
            crossAxisSpacing: 12,
            mainAxisSpacing: 14,
          ),
        ),
      ),
      if (_page < _totalPages)
        SliverPadding(
          padding: EdgeInsets.fromLTRB(
            horizontalPadding,
            20,
            horizontalPadding,
            0,
          ),
          sliver: SliverToBoxAdapter(
            child: OutlinedButton(
              key: const Key('loadMoreCatalogButton'),
              onPressed: _loadingMore
                  ? null
                  : () => _loadProducts(reset: false),
              child: _loadingMore
                  ? const SizedBox.square(
                      dimension: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : Text('Cargar más · página $_page de $_totalPages'),
            ),
          ),
        ),
    ];
  }

  Widget _skeletonGrid(double horizontalPadding) => SliverPadding(
    padding: EdgeInsets.symmetric(horizontal: horizontalPadding),
    sliver: SliverGrid(
      key: const Key('catalogLoadingSkeleton'),
      delegate: SliverChildBuilderDelegate(
        (_, _) => Container(
          decoration: BoxDecoration(
            color: AppColors.white,
            borderRadius: BorderRadius.circular(14),
          ),
          child: Column(
            children: [
              Expanded(child: Container(color: AppColors.line)),
              const Padding(
                padding: EdgeInsets.all(14),
                child: Column(
                  children: [
                    _SkeletonLine(width: double.infinity),
                    SizedBox(height: 8),
                    _SkeletonLine(width: 90),
                  ],
                ),
              ),
            ],
          ),
        ),
        childCount: 6,
      ),
      gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
        maxCrossAxisExtent: 255,
        mainAxisExtent: 335,
        crossAxisSpacing: 12,
        mainAxisSpacing: 14,
      ),
    ),
  );
}

class _SkeletonLine extends StatelessWidget {
  const _SkeletonLine({required this.width});
  final double width;
  @override
  Widget build(BuildContext context) => Align(
    alignment: Alignment.centerLeft,
    child: Container(
      width: width,
      height: 13,
      decoration: BoxDecoration(
        color: AppColors.line,
        borderRadius: BorderRadius.circular(6),
      ),
    ),
  );
}

class _SectionCard extends StatelessWidget {
  const _SectionCard({
    required this.section,
    required this.selected,
    required this.onTap,
  });

  final CatalogSection section;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final foreground = selected ? AppColors.white : AppColors.espresso;
    final icon = switch (section) {
      CatalogSection.hombre => Icons.man_rounded,
      CatalogSection.mujer => Icons.woman_rounded,
      CatalogSection.unisex => Icons.people_outline_rounded,
    };
    return Material(
      key: Key('catalogSection-${section.apiValue}'),
      color: selected ? AppColors.espresso : AppColors.white,
      shape: RoundedRectangleBorder(
        side: BorderSide(color: selected ? AppColors.espresso : AppColors.line),
        borderRadius: BorderRadius.circular(14),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: SizedBox(
          height: 104,
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(icon, color: foreground, size: 29),
              const SizedBox(height: 8),
              Text(
                section.label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  color: foreground,
                  fontSize: 13,
                  fontWeight: FontWeight.w800,
                ),
              ),
              if (selected) ...[
                const SizedBox(height: 3),
                const Text(
                  'Seleccionada',
                  style: TextStyle(color: AppColors.clay, fontSize: 9),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
