import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../cart/cart_screen.dart';
import '../cart/cart_models.dart';
import '../cart/cart_service.dart';
import '../catalog/catalog_screen.dart';
import '../catalog/availability_service.dart';
import '../checkout/checkout_screen.dart';
import '../checkout/checkout_models.dart';
import '../checkout/checkout_service.dart';
import '../home/client_home_screen.dart';
import '../payment/payment_screen.dart';
import '../payment/payment_service.dart';
import '../purchases/purchases_screen.dart';
import '../purchases/purchase_models.dart';
import '../purchases/purchase_service.dart';
import '../returns/return_request_screen.dart';
import '../returns/return_service.dart';
import '../receipts/receipt_screen.dart';
import '../receipts/receipt_service.dart';
import '../recommendations/recommendations_screen.dart';
import '../recommendations/recommendation_service.dart';
import '../profile/change_password_screen.dart';
import '../profile/profile_screen.dart';
import '../reservations/my_reservations_screen.dart';
import '../reservations/reservation_detail_screen.dart';
import '../reservations/reservation_draft.dart';
import '../reservations/reservation_draft_screen.dart';
import '../reservations/reservation_models.dart';
import 'login_models.dart';
import 'login_screen.dart';
import 'login_service.dart';
import 'password_recovery_screen.dart';
import 'register_screen.dart';
import 'session_service.dart';

enum _AuthView {
  loading,
  login,
  register,
  passwordRecovery,
  clientHome,
  catalog,
  cart,
  checkout,
  payment,
  purchases,
  returnRequest,
  receipt,
  recommendations,
  reservationDraft,
  myReservations,
  reservationDetail,
  profile,
  changePassword,
}

class AuthFlow extends StatefulWidget {
  const AuthFlow({super.key});

  @override
  State<AuthFlow> createState() => _AuthFlowState();
}

class _AuthFlowState extends State<AuthFlow> {
  late final SessionService _sessionService;
  late final LoginService _loginService;
  late final CartService _cartService;
  late final CheckoutService _checkoutService;
  late final CatalogAvailabilityService _availabilityService;
  late final PaymentService _paymentService;
  late final PurchaseService _purchaseService;
  late final ReturnService _returnService;
  late final ReceiptService _receiptService;
  late final RecommendationService _recommendationService;
  late final ReservationDraftController _reservationDraft;

  _AuthView _view = _AuthView.loading;
  AuthenticatedUser? _user;
  int? _reservationId;
  ReservationDetail? _initialReservation;
  bool _reservationCreated = false;
  DigitalSale? _paymentSale;
  PurchaseDetail? _returnPurchase;
  int? _receiptSaleId;

  @override
  void initState() {
    super.initState();
    _sessionService = SessionService();
    _loginService = LoginService(sessionService: _sessionService);
    _cartService = CartService();
    _checkoutService = CheckoutService();
    _availabilityService = CatalogAvailabilityService();
    _paymentService = PaymentService();
    _purchaseService = PurchaseService();
    _returnService = ReturnService();
    _receiptService = ReceiptService();
    _recommendationService = RecommendationService();
    _reservationDraft = ReservationDraftController();
    _restoreSession();
  }

  @override
  void dispose() {
    _loginService.close();
    _cartService.close();
    _checkoutService.close();
    _availabilityService.close();
    _paymentService.close();
    _purchaseService.close();
    _returnService.close();
    _receiptService.close();
    _recommendationService.close();
    _reservationDraft.dispose();
    super.dispose();
  }

  Future<void> _addToCart(int variantId, int quantity) async {
    try {
      await _cartService.addItem(variantId, quantity);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Artículo agregado a tu carrito.')),
      );
    } on CartFailure catch (error) {
      if (!mounted) return;
      if (error.invalidatesSession) {
        await _handleInvalidSession(error.message);
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(error.message)),
      );
    }
  }

  Future<void> _restoreSession() async {
    StoredSession? session;
    try {
      session = await _sessionService.restoreSession();
      if (session != null && !session.user.isClient) {
        await _sessionService.logout();
        session = null;
      }
    } catch (_) {
      try {
        await _sessionService.logout();
      } catch (_) {
        // El flujo de acceso sigue disponible si el almacenamiento falla.
      }
    }

    if (!mounted) {
      return;
    }
    setState(() {
      _user = session?.user;
      _view = session == null ? _AuthView.login : _AuthView.clientHome;
    });
  }

  void _onLoginSuccess(AuthenticatedUser user) {
    setState(() {
      _user = user;
      _view = _AuthView.clientHome;
    });
  }

  Future<void> _logout() async {
    try {
      await _sessionService.logout();
      _reservationDraft.clear();
      if (!mounted) {
        return;
      }
      setState(() {
        _user = null;
        _view = _AuthView.login;
      });
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
              'No pudimos cerrar la sesión de forma segura. Inténtalo nuevamente.',
            ),
          ),
        );
      }
    }
  }

  Future<void> _handleInvalidSession(String message) async {
    try {
      await _sessionService.logout();
    } catch (_) {
      // El acceso se bloquea localmente incluso si el almacenamiento falla.
    }
    if (!mounted) {
      return;
    }
    _reservationDraft.clear();
    setState(() {
      _user = null;
      _view = _AuthView.login;
    });
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  Widget build(BuildContext context) {
    final child = switch (_view) {
      _AuthView.loading => const _SessionLoadingScreen(),
      _AuthView.login => LoginScreen(
        loginGateway: _loginService,
        onLoginSuccess: _onLoginSuccess,
        onCreateAccount: () => setState(() => _view = _AuthView.register),
        onForgotPassword: () =>
            setState(() => _view = _AuthView.passwordRecovery),
      ),
      _AuthView.register => RegisterScreen(
        onLoginRequested: () => setState(() => _view = _AuthView.login),
      ),
      _AuthView.passwordRecovery => PasswordRecoveryScreen(
        onBackToLogin: () => setState(() => _view = _AuthView.login),
      ),
      _AuthView.clientHome => ClientHomeScreen(
        user: _user!,
        onLogout: _logout,
        onOpenProfile: () => setState(() => _view = _AuthView.profile),
        onOpenCatalog: () => setState(() => _view = _AuthView.catalog),
        onOpenReservations: () =>
            setState(() => _view = _AuthView.myReservations),
        onOpenCart: () => setState(() => _view = _AuthView.cart),
        onOpenPurchases: () => setState(() => _view = _AuthView.purchases),
        onOpenRecommendations: () => setState(() => _view = _AuthView.recommendations),
      ),
      _AuthView.catalog => CatalogScreen(
        onBack: () => setState(() => _view = _AuthView.clientHome),
        reservationDraft: _reservationDraft,
        onOpenReservationDraft: () =>
            setState(() => _view = _AuthView.reservationDraft),
        onAddToCart: _addToCart,
        onOpenCart: () => setState(() => _view = _AuthView.cart),
      ),
      _AuthView.cart => CartScreen(
        cartGateway: _cartService,
        onBack: () => setState(() => _view = _AuthView.clientHome),
        onOpenCheckout: () => setState(() => _view = _AuthView.checkout),
        onSessionInvalidated: _handleInvalidSession,
      ),
      _AuthView.checkout => CheckoutScreen(
        cartGateway: _cartService,
        checkoutGateway: _checkoutService,
        availabilityGateway: _availabilityService,
        onBack: () => setState(() => _view = _AuthView.cart),
        onOpenPayment: (sale) => setState(() {
          _paymentSale = sale;
          _view = _AuthView.payment;
        }),
        onSessionInvalidated: _handleInvalidSession,
      ),
      _AuthView.payment => PaymentScreen(
        sale: _paymentSale!,
        paymentGateway: _paymentService,
        onBack: () => setState(() => _view = _AuthView.checkout),
        onSessionInvalidated: _handleInvalidSession,
      ),
      _AuthView.purchases => PurchasesScreen(
        purchaseGateway: _purchaseService,
        onBack: () => setState(() => _view = _AuthView.clientHome),
        onOpenReceipt: (saleId) => setState(() {
          _receiptSaleId = saleId;
          _view = _AuthView.receipt;
        }),
        onOpenReturnRequest: (purchase) => setState(() {
          _returnPurchase = purchase;
          _view = _AuthView.returnRequest;
        }),
        onSessionInvalidated: _handleInvalidSession,
      ),
      _AuthView.receipt => ReceiptScreen(
        saleId: _receiptSaleId!,
        receiptGateway: _receiptService,
        onBack: () => setState(() => _view = _AuthView.purchases),
        onSessionInvalidated: _handleInvalidSession,
      ),
      _AuthView.recommendations => RecommendationsScreen(
        recommendationGateway: _recommendationService,
        onBack: () => setState(() => _view = _AuthView.clientHome),
        onSessionInvalidated: _handleInvalidSession,
      ),
      _AuthView.returnRequest => ReturnRequestScreen(
        purchase: _returnPurchase!,
        returnGateway: _returnService,
        onBack: () => setState(() => _view = _AuthView.purchases),
        onSessionInvalidated: _handleInvalidSession,
      ),
      _AuthView.reservationDraft => ReservationDraftScreen(
        draft: _reservationDraft,
        onBack: () => setState(() => _view = _AuthView.catalog),
        onContinueShopping: () => setState(() => _view = _AuthView.catalog),
        onCreated: (reservation) => setState(() {
          _reservationId = reservation.id;
          _initialReservation = reservation;
          _reservationCreated = true;
          _view = _AuthView.reservationDetail;
        }),
        onSessionInvalidated: _handleInvalidSession,
      ),
      _AuthView.myReservations => MyReservationsScreen(
        onBack: () => setState(() => _view = _AuthView.clientHome),
        onOpenDetail: (id) => setState(() {
          _reservationId = id;
          _initialReservation = null;
          _reservationCreated = false;
          _view = _AuthView.reservationDetail;
        }),
        onSessionInvalidated: _handleInvalidSession,
      ),
      _AuthView.reservationDetail => ReservationDetailScreen(
        reservationId: _reservationId!,
        initialReservation: _initialReservation,
        created: _reservationCreated,
        onBack: () => setState(() {
          _initialReservation = null;
          _reservationCreated = false;
          _view = _AuthView.myReservations;
        }),
        onSessionInvalidated: _handleInvalidSession,
      ),
      _AuthView.profile => ProfileScreen(
        onBack: () => setState(() => _view = _AuthView.clientHome),
        onChangePassword: () =>
            setState(() => _view = _AuthView.changePassword),
        onLogout: _logout,
        onSessionInvalidated: _handleInvalidSession,
      ),
      _AuthView.changePassword => ChangePasswordScreen(
        onBackToProfile: () => setState(() => _view = _AuthView.profile),
        onSessionInvalidated: _handleInvalidSession,
      ),
    };

    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 240),
      child: KeyedSubtree(key: ValueKey(_view), child: child),
    );
  }
}

class _SessionLoadingScreen extends StatelessWidget {
  const _SessionLoadingScreen();

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      body: SafeArea(
        child: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                'FASHIONSTORE',
                style: TextStyle(
                  color: AppColors.espresso,
                  fontSize: 15,
                  fontWeight: FontWeight.w800,
                  letterSpacing: 2.4,
                ),
              ),
              SizedBox(height: 20),
              SizedBox.square(
                dimension: 24,
                child: CircularProgressIndicator(strokeWidth: 2.4),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
