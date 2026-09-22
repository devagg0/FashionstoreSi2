import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';
import '../chatbot_models.dart';

class ChatMessageBubble extends StatelessWidget {
  const ChatMessageBubble({super.key, required this.message});

  final ChatMessage message;

  @override
  Widget build(BuildContext context) {
    final isUser = message.role == ChatMessageRole.user;
    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxWidth: MediaQuery.sizeOf(context).width * .82,
        ),
        child: Container(
          margin: const EdgeInsets.only(bottom: 12),
          padding: const EdgeInsets.symmetric(horizontal: 15, vertical: 12),
          decoration: BoxDecoration(
            color: isUser ? AppColors.espresso : AppColors.white,
            border: Border.all(
              color: isUser ? AppColors.espresso : AppColors.line,
            ),
            borderRadius: BorderRadius.circular(14),
          ),
          child: Text(
            message.content,
            style: TextStyle(
              color: isUser ? AppColors.white : AppColors.espresso,
              fontSize: 14,
              height: 1.45,
            ),
          ),
        ),
      ),
    );
  }
}
