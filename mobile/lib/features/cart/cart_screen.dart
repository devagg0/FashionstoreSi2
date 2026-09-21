import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../auth/widgets/auth_components.dart';
import '../catalog/widgets/catalog_widgets.dart';
import 'cart_models.dart';
import 'cart_service.dart';
import 'widgets/cart_item_tile.dart';

class CartScreen extends StatefulWidget {
  const CartScreen({
    super.key,
    this.cartGateway,
    required this.onBack,
    this.onOpenCheckout,
    this.onSessionInvalidated,
  });

  final CartGateway? cartGateway;
  final VoidCallback onBack;
  final VoidCallback? onOpenCheckout;
  final Future<void> Function(String message)? onSessionInvalidated;

  @override
  State<CartScreen> createState() => _CartScreenState();
}

class _CartScreenState extends State<CartScreen> {
  late final CartGateway _gateway;
  late final bool _ownsService;

  CartData? _cart;
  String? _errorMessage;
  bool _loading = true;
  bool _isClearing = false;
  bool _isLeavingInvalidSession = false;

  @override
  void initState() {
    super.initState();
    _ownsService = widget.cartGateway == null;
    _gateway = widget.cartGateway ?? CartService();
    _loadCart();
  }

  @override
  void dispose() {
    if (_ownsService && _gateway is CartService) {
      _gateway.close();
    }
    super.dispose();
  }

  Future<void> _loadCart() async {
    setState(() {
      _loading = true;
      _errorMessage = null;
    });

    try {
      final cart = await _gateway.loadCart();
      if (!mounted) return;
      setState(() => _cart = cart);
    } on CartFailure catch (error) {
      if (!mounted) return;
      if (error.invalidatesSession && widget.onSessionInvalidated != null) {
        setState(() => _isLeavingInvalidSession = true);
        await widget.onSessionInvalidated!(error.message);
        return;
      }
      setState(() => _errorMessage = error.message);
    } catch (_) {
      if (mounted) {
        setState(() => _errorMessage = 'No pudimos cargar tu carrito.');
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _updateQuantity(int variantId, int nextQuantity) async {
    if (nextQuantity < 1) return;
    try {
      final updated = await _gateway.updateItem(variantId, nextQuantity);
      if (!mounted) return;
      setState(() => _cart = updated);
    } on CartFailure catch (error) {
      if (mounted) {
        setState(() => _errorMessage = error.message);
      }
    }
  }

  Future<void> _removeItem(int variantId) async {
    try {
      final updated = await _gateway.deleteItem(variantId);
      if (!mounted) return;
      setState(() => _cart = updated);
    } on CartFailure catch (error) {
      if (mounted) {
        setState(() => _errorMessage = error.message);
      }
    }
  }

  Future<void> _clearCart() async {
    if (_isClearing) return;
    setState(() => _isClearing = true);
    try {
      final updated = await _gateway.clearCart();
      if (!mounted) return;
      setState(() => _cart = updated);
    } on CartFailure catch (error) {
      if (mounted) {
        setState(() => _errorMessage = error.message);
      }
    } finally {
      if (mounted) setState(() => _isClearing = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final horizontalPadding = MediaQuery.sizeOf(context).width < 370
        ? 18.0
        : 22.0;

    return Scaffold(
      body: SafeArea(
        child: CustomScrollView(
          key: const Key('cartScrollView'),
          slivers: [
            SliverAppBar(
              pinned: true,
              backgroundColor: AppColors.linen,
              surfaceTintColor: AppColors.linen,
              leading: IconButton(
                key: const Key('cartBackButton'),
                tooltip: 'Volver',
                onPressed: widget.onBack,
                icon: const Icon(Icons.arrow_back_rounded),
              ),
              title: const Text('MI CARRITO'),
            ),
            SliverPadding(
              padding: EdgeInsets.fromLTRB(
                horizontalPadding,
                18,
                horizontalPadding,
                32,
              ),
              sliver: SliverToBoxAdapter(
                child: Center(
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 720),
                    child: AnimatedSwitcher(
                      duration: const Duration(milliseconds: 220),
                      child: _body(),
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

  Widget _body() {
    if (_loading || _isLeavingInvalidSession) {
      return const _CartLoading(key: ValueKey('cartLoading'));
    }
    if (_errorMessage != null) {
      return _CartError(
        key: const ValueKey('cartError'),
        message: _errorMessage!,
        onRetry: _loadCart,
      );
    }
    final cart = _cart ?? const CartData(items: [], quantityItems: 0, quantityUnits: 0, subtotal: 0, discountTotal: 0, total: 0);
    if (cart.items.isEmpty) {
      return const _EmptyCart(key: ValueKey('emptyCart'));
    }

    return Column(
      key: const ValueKey('cartContent'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            const Expanded(
              child: Text(
                'ARTÍCULOS',
                style: TextStyle(
                  color: AppColors.terracotta,
                  fontSize: 11,
                  fontWeight: FontWeight.w800,
                  letterSpacing: 2,
                ),
              ),
            ),
            if (cart.items.isNotEmpty)
              TextButton.icon(
                key: const Key('clearCartButton'),
                onPressed: _isClearing ? null : _clearCart,
                icon: const Icon(Icons.remove_circle_outline_rounded),
                label: const Text('Vaciar'),
              ),
          ],
        ),
        const SizedBox(height: 14),
        ...cart.items.map(
          (item) => Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: CartItemTile(
              item: item,
              onDecrease: () => _updateQuantity(item.variantId, item.quantity - 1),
              onIncrease: () => _updateQuantity(item.variantId, item.quantity + 1),
              onRemove: () => _removeItem(item.variantId),
            ),
          ),
        ),
        const SizedBox(height: 18),
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(18),
          decoration: BoxDecoration(
            color: AppColors.white,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: AppColors.line),
          ),
          child: Column(
            children: [
              _totalRow('Subtotal', cart.subtotal),
              const SizedBox(height: 8),
              _totalRow('Descuento', cart.discountTotal, isDiscount: true),
              const Divider(height: 20),
              _totalRow('Total', cart.total, isTotal: true),
              if (widget.onOpenCheckout != null) ...[
                const SizedBox(height: 16),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton.icon(
                    key: const Key('openCheckoutButton'),
                    onPressed: widget.onOpenCheckout,
                    icon: const Icon(Icons.shopping_bag_outlined),
                    label: const Text('Continuar con la compra'),
                  ),
                ),
              ],
            ],
          ),
        ),
      ],
    );
  }

  Widget _totalRow(String label, double amount, {bool isDiscount = false, bool isTotal = false}) =>
      Row(
        children: [
          Text(
            label,
            style: TextStyle(
              color: isTotal ? AppColors.espresso : AppColors.muted,
              fontWeight: isTotal ? FontWeight.w800 : FontWeight.w600,
            ),
          ),
          const Spacer(),
          Text(
            formatCatalogMoney(amount),
            style: TextStyle(
              color: isTotal ? AppColors.espresso : AppColors.muted,
              fontSize: isTotal ? 18 : 15,
              fontWeight: isTotal ? FontWeight.w800 : FontWeight.w700,
            ),
          ),
        ],
      );
}

class _CartLoading extends StatelessWidget {
  const _CartLoading({super.key});

  @override
  Widget build(BuildContext context) {
    return const Column(
      children: [
        SizedBox(height: 60),
        CircularProgressIndicator(),
        SizedBox(height: 16),
        Text('Cargando carrito...'),
      ],
    );
  }
}

class _CartError extends StatelessWidget {
  const _CartError({
    super.key,
    required this.message,
    required this.onRetry,
  });

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        AuthStatusBanner(message: message),
        const SizedBox(height: 18),
        FilledButton.icon(
          key: const Key('retryCartButton'),
          onPressed: onRetry,
          icon: const Icon(Icons.refresh_rounded),
          label: const Text('Reintentar'),
        ),
      ],
    );
  }
}

class _EmptyCart extends StatelessWidget {
  const _EmptyCart({super.key});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        const Icon(
          Icons.shopping_cart_outlined,
          size: 52,
          color: AppColors.terracotta,
        ),
        const SizedBox(height: 18),
        const Text(
          'Tu carrito está vacío.',
          style: TextStyle(
            color: AppColors.espresso,
            fontSize: 20,
            fontWeight: FontWeight.w700,
          ),
        ),
        const SizedBox(height: 8),
        const Text(
          'Agrega prendas desde el catálogo para comenzar.',
          textAlign: TextAlign.center,
          style: TextStyle(color: AppColors.muted),
        ),
        const SizedBox(height: 22),
        FilledButton.icon(
          key: const Key('emptyCartBackButton'),
          onPressed: () => Navigator.of(context).pop(),
          icon: const Icon(Icons.arrow_back_rounded),
          label: const Text('Volver al catálogo'),
        ),
      ],
    );
  }
}
