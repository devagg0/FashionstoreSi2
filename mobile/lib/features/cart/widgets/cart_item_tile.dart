import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';
import '../../catalog/widgets/catalog_widgets.dart';
import '../cart_models.dart';

class CartItemTile extends StatelessWidget {
  const CartItemTile({
    super.key,
    required this.item,
    required this.onDecrease,
    required this.onIncrease,
    required this.onRemove,
  });

  final CartItem item;
  final VoidCallback onDecrease;
  final VoidCallback onIncrease;
  final VoidCallback onRemove;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppColors.line),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 84,
            height: 94,
            child: ClipRRect(
              borderRadius: BorderRadius.circular(10),
              child: CatalogImageView(
                imageUrl: item.imageUrl,
                fit: BoxFit.cover,
                semanticLabel: item.productName,
              ),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: Text(
                        item.productName,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          color: AppColors.espresso,
                          fontSize: 15,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                    IconButton(
                      tooltip: 'Eliminar producto',
                      onPressed: onRemove,
                      icon: const Icon(Icons.delete_outline_rounded),
                      color: AppColors.error,
                    ),
                  ],
                ),
                const SizedBox(height: 6),
                Text(
                  '${item.size.name} · ${item.color.name}',
                  style: const TextStyle(
                    color: AppColors.muted,
                    fontSize: 12,
                  ),
                ),
                const SizedBox(height: 6),
                Text(
                  'SKU: ${item.sku}',
                  style: const TextStyle(
                    color: AppColors.muted,
                    fontSize: 11.5,
                  ),
                ),
                const SizedBox(height: 10),
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        formatCatalogMoney(item.subtotal),
                        style: const TextStyle(
                          color: AppColors.espresso,
                          fontSize: 16,
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                    ),
                    Row(
                      children: [
                        IconButton.outlined(
                          key: Key('decreaseCartQty-${item.variantId}'),
                          onPressed: item.quantity > 1 ? onDecrease : null,
                          icon: const Icon(Icons.remove_rounded),
                        ),
                        SizedBox(
                          width: 38,
                          child: Text(
                            '${item.quantity}',
                            textAlign: TextAlign.center,
                            style: const TextStyle(
                              color: AppColors.espresso,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ),
                        IconButton.outlined(
                          key: Key('increaseCartQty-${item.variantId}'),
                          onPressed: item.quantity < item.availability
                              ? onIncrease
                              : null,
                          icon: const Icon(Icons.add_rounded),
                        ),
                      ],
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
