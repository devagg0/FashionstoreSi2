import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../auth/widgets/auth_components.dart';
import 'chatbot_models.dart';
import 'chatbot_service.dart';
import 'widgets/chat_message_bubble.dart';

class ChatbotScreen extends StatefulWidget {
  const ChatbotScreen({
    super.key,
    this.chatbotGateway,
    required this.onBack,
    this.onSessionInvalidated,
  });

  final ChatbotGateway? chatbotGateway;
  final VoidCallback onBack;
  final Future<void> Function(String message)? onSessionInvalidated;

  @override
  State<ChatbotScreen> createState() => _ChatbotScreenState();
}

class _ChatbotScreenState extends State<ChatbotScreen> {
  late final ChatbotGateway _gateway;
  late final bool _ownsService;
  final _controller = TextEditingController();
  final _scrollController = ScrollController();
  final List<ChatMessage> _messages = [
    const ChatMessage(
      role: ChatMessageRole.assistant,
      content: 'Hola. Puedo ayudarte a encontrar prendas, revisar disponibilidad o elegir un look.',
    ),
  ];
  List<ChatbotProduct> _products = const [];
  String? _errorMessage;
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    _ownsService = widget.chatbotGateway == null;
    _gateway = widget.chatbotGateway ?? ChatbotService();
  }

  @override
  void dispose() {
    _controller.dispose();
    _scrollController.dispose();
    if (_ownsService) {
      final gateway = _gateway;
      if (gateway is ChatbotService) gateway.close();
    }
    super.dispose();
  }

  Future<void> _send() async {
    final message = _controller.text.trim();
    if (message.isEmpty || _loading) return;
    final history = List<ChatMessage>.unmodifiable(_messages);
    setState(() {
      _messages.add(ChatMessage(role: ChatMessageRole.user, content: message));
      _controller.clear();
      _errorMessage = null;
      _loading = true;
    });
    _scrollToBottom();
    try {
      final response = await _gateway.sendMessage(
        message: message,
        history: history,
      );
      if (!mounted) return;
      setState(() {
        _messages.add(
          ChatMessage(role: ChatMessageRole.assistant, content: response.reply),
        );
        _products = response.products;
      });
      _scrollToBottom();
    } on ChatbotFailure catch (error) {
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

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 220),
          curve: Curves.easeOut,
        );
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final padding = MediaQuery.sizeOf(context).width < 370 ? 18.0 : 22.0;
    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            _header(),
            Expanded(
              child: ListView(
                controller: _scrollController,
                padding: EdgeInsets.fromLTRB(padding, 22, padding, 10),
                children: [
                  ..._messages.map(
                    (message) => ChatMessageBubble(message: message),
                  ),
                  if (_loading) const _TypingIndicator(),
                  if (_errorMessage != null) ...[
                    const SizedBox(height: 4),
                    AuthStatusBanner(message: _errorMessage!),
                  ],
                  if (_products.isNotEmpty) ...[
                    const SizedBox(height: 10),
                    const Text(
                      'Prendas sugeridas',
                      style: TextStyle(
                        color: AppColors.espresso,
                        fontSize: 19,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                    const SizedBox(height: 10),
                    ..._products.map(_productCard),
                  ],
                ],
              ),
            ),
            _composer(padding),
          ],
        ),
      ),
    );
  }

  Widget _header() => Container(
    padding: const EdgeInsets.fromLTRB(18, 12, 18, 16),
    decoration: const BoxDecoration(
      gradient: LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [AppColors.clay, AppColors.terracotta],
      ),
    ),
    child: Row(
      children: [
        IconButton(
          key: const Key('chatbotBackButton'),
          tooltip: 'Volver',
          onPressed: widget.onBack,
          icon: const Icon(Icons.arrow_back_rounded, color: AppColors.espresso),
        ),
        const Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'FASHIONSTORE',
                style: TextStyle(
                  color: AppColors.espresso,
                  fontSize: 11,
                  fontWeight: FontWeight.w800,
                  letterSpacing: 2,
                ),
              ),
              SizedBox(height: 4),
              Text(
                'Asistente de estilo',
                style: TextStyle(
                  color: AppColors.espresso,
                  fontSize: 21,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ],
          ),
        ),
        const Icon(Icons.auto_awesome_outlined, color: AppColors.espresso),
      ],
    ),
  );

  Widget _composer(double padding) => Material(
    color: AppColors.white,
    child: Padding(
      padding: EdgeInsets.fromLTRB(padding, 10, padding, 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Expanded(
            child: TextField(
              key: const Key('chatbotMessageField'),
              controller: _controller,
              minLines: 1,
              maxLines: 4,
              textInputAction: TextInputAction.newline,
              decoration: const InputDecoration(
                hintText: '¿Qué prenda estás buscando?',
                prefixIcon: Icon(Icons.chat_bubble_outline_rounded),
              ),
              onSubmitted: (_) => _send(),
            ),
          ),
          const SizedBox(width: 8),
          IconButton.filled(
            key: const Key('chatbotSendButton'),
            tooltip: 'Enviar mensaje',
            onPressed: _loading ? null : _send,
            icon: _loading
                ? const SizedBox.square(
                    dimension: 19,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.arrow_upward_rounded),
          ),
        ],
      ),
    ),
  );

  Widget _productCard(ChatbotProduct product) => Container(
    margin: const EdgeInsets.only(bottom: 10),
    padding: const EdgeInsets.all(14),
    decoration: BoxDecoration(
      color: AppColors.white,
      border: Border.all(color: AppColors.line),
      borderRadius: BorderRadius.circular(12),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: Text(
                product.name,
                style: const TextStyle(
                  color: AppColors.espresso,
                  fontSize: 16,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ),
            const SizedBox(width: 8),
            Text(
              'Bs ${product.price.toStringAsFixed(2)}',
              style: const TextStyle(
                color: AppColors.terracotta,
                fontWeight: FontWeight.w800,
              ),
            ),
          ],
        ),
        const SizedBox(height: 5),
        Text(
          product.category,
          style: const TextStyle(
            color: AppColors.muted,
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(height: 7),
        Text(
          'Colores: ${product.colors.join(', ')} · Tallas: ${product.sizes.join(', ')}',
          style: const TextStyle(color: AppColors.muted, fontSize: 13),
        ),
        if (product.availability != null) ...[
          const SizedBox(height: 5),
          Text(
            product.availableQuantity == null
                ? product.availability!
                : '${product.availability} · ${product.availableQuantity} unidades',
            style: const TextStyle(
              color: AppColors.success,
              fontSize: 13,
              fontWeight: FontWeight.w700,
            ),
          ),
        ],
      ],
    ),
  );
}

class _TypingIndicator extends StatelessWidget {
  const _TypingIndicator();

  @override
  Widget build(BuildContext context) => const Align(
    alignment: Alignment.centerLeft,
    child: Padding(
      padding: EdgeInsets.only(bottom: 12),
      child: Text(
        'El asistente está revisando el catálogo...',
        style: TextStyle(color: AppColors.muted, fontSize: 13),
      ),
    ),
  );
}
