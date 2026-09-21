import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../auth/widgets/auth_components.dart';
import '../cart/cart_models.dart';
import '../cart/cart_service.dart';
import '../catalog/availability_models.dart';
import '../catalog/availability_service.dart';
import '../catalog/widgets/catalog_widgets.dart';
import 'checkout_models.dart';
import 'checkout_service.dart';

class CheckoutScreen extends StatefulWidget {
  const CheckoutScreen({
    super.key,
    required this.cartGateway,
    this.checkoutGateway,
    this.availabilityGateway,
    required this.onBack,
    this.onOpenPayment,
    this.onSessionInvalidated,
  });

  final CartGateway cartGateway;
  final CheckoutGateway? checkoutGateway;
  final CatalogAvailabilityGateway? availabilityGateway;
  final VoidCallback onBack;
  final ValueChanged<DigitalSale>? onOpenPayment;
  final Future<void> Function(String message)? onSessionInvalidated;

  @override
  State<CheckoutScreen> createState() => _CheckoutScreenState();
}

class _CheckoutScreenState extends State<CheckoutScreen> {
  late final CheckoutGateway _checkout;
  late final CatalogAvailabilityGateway _availability;
  late final bool _ownsCheckout;
  late final bool _ownsAvailability;

  CartData? _cart;
  DigitalSale? _sale;
  List<BranchAvailability> _eligibleBranches = const [];
  int? _selectedBranchId;
  String? _errorMessage;
  bool _loading = true;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    _ownsCheckout = widget.checkoutGateway == null;
    _ownsAvailability = widget.availabilityGateway == null;
    _checkout = widget.checkoutGateway ?? CheckoutService();
    _availability = widget.availabilityGateway ?? CatalogAvailabilityService();
    _load();
  }

  @override
  void dispose() {
    if (_ownsCheckout && _checkout is CheckoutService) _checkout.close();
    if (_ownsAvailability && _availability is CatalogAvailabilityService) {
      _availability.close();
    }
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _errorMessage = null;
    });
    try {
      final cart = await widget.cartGateway.loadCart();
      if (!mounted) return;
      if (cart.items.isEmpty || cart.idCarrito == null) {
        setState(() {
          _cart = cart;
          _eligibleBranches = const [];
          _loading = false;
        });
        return;
      }

      final availability = await Future.wait(
        cart.items.map(
          (item) => _availability.loadVariantAvailability(
            productId: item.productId,
            variantId: item.variantId,
          ),
        ),
      );
      final branches = _intersectBranches(cart.items, availability);
      if (!mounted) return;
      setState(() {
        _cart = cart;
        _eligibleBranches = branches;
        _selectedBranchId = branches.isEmpty ? null : branches.first.branchId;
      });
    } on CartFailure catch (error) {
      await _handleFailure(error.message, invalidatesSession: error.invalidatesSession);
    } on AvailabilityFailure catch (error) {
      await _handleFailure(error.message);
    } on CheckoutFailure catch (error) {
      await _handleFailure(error.message, invalidatesSession: error.invalidatesSession);
    } catch (_) {
      await _handleFailure('No pudimos preparar el resumen de compra.');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  List<BranchAvailability> _intersectBranches(
    List<CartItem> items,
    List<CatalogAvailabilityResult> responses,
  ) {
    if (items.isEmpty || responses.length != items.length) return const [];
    final first = responses.first.branches.where(
      (branch) => branch.availableStock >= items.first.quantity,
    );
    final eligible = <int, BranchAvailability>{
      for (final branch in first) branch.branchId: branch,
    };
    for (var index = 1; index < responses.length; index++) {
      final availableIds = responses[index].branches
          .where((branch) => branch.availableStock >= items[index].quantity)
          .map((branch) => branch.branchId)
          .toSet();
      eligible.removeWhere((branchId, _) => !availableIds.contains(branchId));
    }
    return eligible.values.toList(growable: false);
  }

  Future<void> _confirm() async {
    final cart = _cart;
    final branchId = _selectedBranchId;
    if (_saving || cart?.idCarrito == null || branchId == null || cart!.items.isEmpty) {
      return;
    }
    setState(() {
      _saving = true;
      _errorMessage = null;
    });
    try {
      final sale = await _checkout.confirmCheckout(
        cartId: cart.idCarrito!,
        branchId: branchId,
      );
      if (!mounted) return;
      setState(() => _sale = sale);
    } on CheckoutFailure catch (error) {
      await _handleFailure(error.message, invalidatesSession: error.invalidatesSession);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _handleFailure(
    String message, {
    bool invalidatesSession = false,
  }) async {
    if (!mounted) return;
    if (invalidatesSession && widget.onSessionInvalidated != null) {
      await widget.onSessionInvalidated!(message);
      return;
    }
    setState(() => _errorMessage = message);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: CustomScrollView(
          slivers: [
            SliverAppBar(
              pinned: true,
              backgroundColor: AppColors.linen,
              surfaceTintColor: AppColors.linen,
              leading: IconButton(
                key: const Key('checkoutBackButton'),
                tooltip: 'Volver al carrito',
                onPressed: widget.onBack,
                icon: const Icon(Icons.arrow_back_rounded),
              ),
              title: const Text('CONFIRMAR COMPRA'),
            ),
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(22, 18, 22, 32),
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
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_errorMessage != null) {
      return Column(
        children: [
          AuthStatusBanner(message: _errorMessage!),
          const SizedBox(height: 18),
          FilledButton.icon(
            key: const Key('retryCheckoutButton'),
            onPressed: _load,
            icon: const Icon(Icons.refresh_rounded),
            label: const Text('Reintentar'),
          ),
        ],
      );
    }
    final sale = _sale;
    if (sale != null) return _saleCreated(sale);
    final cart = _cart;
    if (cart == null || cart.items.isEmpty) {
      return const _CheckoutEmpty();
    }
    return _checkoutSummary(cart);
  }

  Widget _checkoutSummary(CartData cart) {
    return Column(
      key: const ValueKey('checkoutSummary'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'RESUMEN DE COMPRA',
          style: TextStyle(
            color: AppColors.terracotta,
            fontSize: 11,
            fontWeight: FontWeight.w800,
            letterSpacing: 2,
          ),
        ),
        const SizedBox(height: 14),
        ...cart.items.map(_cartItemRow),
        const SizedBox(height: 12),
        _totals(cart.subtotal, cart.discountTotal, cart.total),
        const SizedBox(height: 22),
        if (_eligibleBranches.isEmpty)
          const AuthStatusBanner(
            message: 'Ninguna sucursal tiene stock suficiente para toda la compra.',
          )
        else ...[
          const Text(
            'SUCURSAL DE RETIRO',
            style: TextStyle(
              color: AppColors.terracotta,
              fontSize: 11,
              fontWeight: FontWeight.w800,
              letterSpacing: 2,
            ),
          ),
          const SizedBox(height: 8),
          DropdownButtonFormField<int>(
            key: const Key('checkoutBranchField'),
            initialValue: _selectedBranchId,
            isExpanded: true,
            decoration: const InputDecoration(labelText: 'Sucursal'),
            items: _eligibleBranches
                .map(
                  (branch) => DropdownMenuItem<int>(
                    value: branch.branchId,
                    child: SizedBox(
                      width: double.infinity,
                      child: Text(
                        '${branch.branchName} · ${branch.cityName}',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  ),
                )
                .toList(growable: false),
            onChanged: _saving
                ? null
                : (value) => setState(() => _selectedBranchId = value),
          ),
          const SizedBox(height: 18),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              key: const Key('confirmDigitalPurchaseButton'),
              onPressed: _saving ? null : _confirm,
              icon: _saving
                  ? const SizedBox.square(
                      dimension: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.check_circle_outline_rounded),
              label: Text(_saving ? 'Creando compra...' : 'Confirmar compra'),
            ),
          ),
        ],
      ],
    );
  }

  Widget _saleCreated(DigitalSale sale) {
    final cartItems = {
      for (final item in _cart?.items ?? const <CartItem>[]) item.variantId: item,
    };
    return Column(
      key: const ValueKey('digitalSaleCreated'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Icon(Icons.check_circle_rounded, color: AppColors.terracotta, size: 48),
        const SizedBox(height: 14),
        const Text(
          'Compra creada',
          style: TextStyle(color: AppColors.espresso, fontSize: 24, fontWeight: FontWeight.w800),
        ),
        const SizedBox(height: 18),
        _saleInfo('Código de compra', sale.purchaseCode),
        _saleInfo('Estado inicial', sale.state),
        _saleInfo('Total', formatCatalogMoney(sale.total)),
        const SizedBox(height: 18),
        const Text('PRODUCTOS', style: TextStyle(color: AppColors.terracotta, fontSize: 11, fontWeight: FontWeight.w800, letterSpacing: 2)),
        const SizedBox(height: 10),
        ...sale.items.map(
          (item) => _saleItemRow(item, cartItems[item.variantId]?.productName),
        ),
        const SizedBox(height: 24),
        SizedBox(
          width: double.infinity,
          child: OutlinedButton.icon(
            key: const Key('continuePaymentButton'),
            onPressed: widget.onOpenPayment == null
                ? null
                : () => widget.onOpenPayment!(sale),
            icon: const Icon(Icons.credit_card_rounded),
            label: const Text('Continuar al pago'),
          ),
        ),
        const SizedBox(height: 10),
        SizedBox(
          width: double.infinity,
          child: TextButton.icon(
            key: const Key('saleBackToCartButton'),
            onPressed: widget.onBack,
            icon: const Icon(Icons.arrow_back_rounded),
            label: const Text('Volver al carrito'),
          ),
        ),
      ],
    );
  }

  Widget _cartItemRow(CartItem item) => Container(
    width: double.infinity,
    margin: const EdgeInsets.only(bottom: 10),
    padding: const EdgeInsets.all(14),
    decoration: BoxDecoration(
      color: AppColors.white,
      borderRadius: BorderRadius.circular(12),
      border: Border.all(color: AppColors.line),
    ),
    child: Row(
      children: [
        Expanded(child: Text('${item.productName}\n${item.size.name} · ${item.color.name}')),
        const SizedBox(width: 10),
        Flexible(
          child: Text(
            '${item.quantity} x ${formatCatalogMoney(item.finalPrice)}',
            textAlign: TextAlign.right,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontWeight: FontWeight.w700),
          ),
        ),
      ],
    ),
  );

  Widget _saleItemRow(DigitalSaleItem item, String? name) => Padding(
    padding: const EdgeInsets.only(bottom: 10),
    child: Row(
      children: [
        Expanded(child: Text(name ?? 'Variante #${item.variantId}')),
        const SizedBox(width: 10),
        Flexible(
          child: Text(
            '${item.quantity} x ${formatCatalogMoney(item.unitPrice - item.unitDiscount)}',
            textAlign: TextAlign.right,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontWeight: FontWeight.w700),
          ),
        ),
      ],
    ),
  );

  Widget _totals(double subtotal, double discount, double total) => Container(
    width: double.infinity,
    padding: const EdgeInsets.all(16),
    decoration: BoxDecoration(color: AppColors.white, borderRadius: BorderRadius.circular(12), border: Border.all(color: AppColors.line)),
    child: Column(
      children: [
        _saleInfo('Subtotal', formatCatalogMoney(subtotal)),
        _saleInfo('Descuento', formatCatalogMoney(discount)),
        const Divider(height: 18),
        _saleInfo('Total', formatCatalogMoney(total), strong: true),
      ],
    ),
  );

  Widget _saleInfo(String label, String value, {bool strong = false}) => Padding(
    padding: const EdgeInsets.only(bottom: 8),
    child: Row(
      children: [
        Flexible(
          child: Text(
            label,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(color: strong ? AppColors.espresso : AppColors.muted, fontWeight: strong ? FontWeight.w800 : FontWeight.w600),
          ),
        ),
        const Spacer(),
        const SizedBox(width: 12),
        Flexible(
          child: Text(
            value,
            textAlign: TextAlign.right,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(color: AppColors.espresso, fontWeight: strong ? FontWeight.w800 : FontWeight.w700),
          ),
        ),
      ],
    ),
  );
}

class _CheckoutEmpty extends StatelessWidget {
  const _CheckoutEmpty();

  @override
  Widget build(BuildContext context) => const Column(
    children: [
      Icon(Icons.shopping_cart_outlined, size: 50, color: AppColors.terracotta),
      SizedBox(height: 16),
      Text('No hay productos para comprar.', style: TextStyle(fontSize: 19, fontWeight: FontWeight.w700)),
      SizedBox(height: 8),
      Text('Regresa al catálogo y agrega una prenda.', textAlign: TextAlign.center),
    ],
  );
}
