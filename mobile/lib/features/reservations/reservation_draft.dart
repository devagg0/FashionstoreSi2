import 'package:flutter/foundation.dart';

import '../catalog/availability_models.dart';
import '../catalog/catalog_models.dart';

class ReservationContext {
  const ReservationContext({
    required this.branchId,
    required this.branchName,
    required this.cityName,
    required this.address,
    required this.openingTime,
    required this.closingTime,
    required this.date,
    required this.time,
  });

  final int branchId;
  final String branchName;
  final String cityName;
  final String address;
  final String openingTime;
  final String closingTime;
  final String date;
  final String time;

  String get scheduledAt =>
      '$date'
      'T$time:00-04:00';
}

class ReservationDraftItem {
  const ReservationDraftItem({
    required this.productId,
    required this.variantId,
    required this.productName,
    required this.imageUrl,
    required this.sku,
    required this.size,
    required this.color,
    required this.referencePrice,
    required this.quantity,
    required this.availableStock,
  });

  final int productId;
  final int variantId;
  final String productName;
  final String? imageUrl;
  final String sku;
  final CatalogSize size;
  final CatalogColor color;
  final double referencePrice;
  final int quantity;
  final int availableStock;

  ReservationDraftItem copyWith({required int quantity}) =>
      ReservationDraftItem(
        productId: productId,
        variantId: variantId,
        productName: productName,
        imageUrl: imageUrl,
        sku: sku,
        size: size,
        color: color,
        referencePrice: referencePrice,
        quantity: quantity,
        availableStock: availableStock,
      );
}

class ReservationDraftController extends ChangeNotifier {
  ReservationContext? _context;
  final List<ReservationDraftItem> _items = [];

  ReservationContext? get context => _context;
  List<ReservationDraftItem> get items => List.unmodifiable(_items);
  bool get isEmpty => _items.isEmpty;
  int get itemCount => _items.fold(0, (total, item) => total + item.quantity);
  double get referenceTotal => _items.fold(
    0,
    (total, item) => total + item.referencePrice * item.quantity,
  );

  bool start(ReservationContext context, ReservationDraftItem item) {
    if (_items.isNotEmpty ||
        !_validQuantity(item.quantity, item.availableStock)) {
      return false;
    }
    _context = context;
    _items.add(item);
    notifyListeners();
    return true;
  }

  bool add(ReservationDraftItem item) {
    if (_context == null ||
        !_validQuantity(item.quantity, item.availableStock)) {
      return false;
    }
    final index = _items.indexWhere((row) => row.variantId == item.variantId);
    if (index < 0) {
      _items.add(item);
    } else {
      final quantity = _items[index].quantity + item.quantity;
      if (!_validQuantity(quantity, item.availableStock)) return false;
      _items[index] = item.copyWith(quantity: quantity);
    }
    notifyListeners();
    return true;
  }

  bool updateQuantity(int variantId, int quantity) {
    final index = _items.indexWhere((item) => item.variantId == variantId);
    if (index < 0 || !_validQuantity(quantity, _items[index].availableStock)) {
      return false;
    }
    _items[index] = _items[index].copyWith(quantity: quantity);
    notifyListeners();
    return true;
  }

  void remove(int variantId) {
    _items.removeWhere((item) => item.variantId == variantId);
    if (_items.isEmpty) _context = null;
    notifyListeners();
  }

  void clear() {
    _items.clear();
    _context = null;
    notifyListeners();
  }

  Map<String, dynamic>? toRequestBody() {
    final current = _context;
    if (current == null || _items.isEmpty) return null;
    return {
      'id_sucursal': current.branchId,
      'fecha_atencion_programada': current.scheduledAt,
      'items': _items
          .map(
            (item) => {
              'id_variante_producto': item.variantId,
              'cantidad': item.quantity,
            },
          )
          .toList(growable: false),
    };
  }

  static bool _validQuantity(int quantity, int stock) =>
      quantity > 0 && quantity <= stock;
}

ReservationContext contextFromBranch({
  required BranchAvailability branch,
  required String date,
  required String time,
}) => ReservationContext(
  branchId: branch.branchId,
  branchName: branch.branchName,
  cityName: branch.cityName,
  address: branch.address,
  openingTime: branch.openingTime!,
  closingTime: branch.closingTime!,
  date: date,
  time: time,
);
