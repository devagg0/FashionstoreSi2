import 'package:flutter/material.dart';

abstract final class AppColors {
  static const espresso = Color(0xFF2B2625);
  static const terracotta = Color(0xFFC87D55);
  static const clay = Color(0xFFE2A882);
  static const linen = Color(0xFFF4EBE1);
  static const white = Color(0xFFFFFFFF);
  static const muted = Color(0xFF746B67);
  static const line = Color(0xFFE1DCD8);
  static const error = Color(0xFF9D513D);
  static const success = Color(0xFF67683F);
}

abstract final class AppTheme {
  static ThemeData get light {
    const colorScheme = ColorScheme.light(
      primary: AppColors.espresso,
      onPrimary: AppColors.white,
      secondary: AppColors.terracotta,
      onSecondary: AppColors.white,
      surface: AppColors.white,
      onSurface: AppColors.espresso,
      error: AppColors.error,
      onError: AppColors.white,
    );

    final border = OutlineInputBorder(
      borderRadius: BorderRadius.circular(10),
      borderSide: const BorderSide(color: AppColors.line),
    );

    return ThemeData(
      useMaterial3: true,
      colorScheme: colorScheme,
      scaffoldBackgroundColor: AppColors.linen,
      fontFamily: 'sans-serif',
      textSelectionTheme: const TextSelectionThemeData(
        cursorColor: AppColors.terracotta,
        selectionColor: Color(0x40E2A882),
        selectionHandleColor: AppColors.terracotta,
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: AppColors.white,
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 16,
          vertical: 17,
        ),
        labelStyle: const TextStyle(color: AppColors.muted),
        hintStyle: const TextStyle(color: Color(0xFF9A918D)),
        prefixIconColor: AppColors.muted,
        suffixIconColor: AppColors.muted,
        border: border,
        enabledBorder: border,
        focusedBorder: border.copyWith(
          borderSide: const BorderSide(color: AppColors.terracotta, width: 1.4),
        ),
        errorBorder: border.copyWith(
          borderSide: const BorderSide(color: AppColors.error),
        ),
        focusedErrorBorder: border.copyWith(
          borderSide: const BorderSide(color: AppColors.error, width: 1.4),
        ),
        errorStyle: const TextStyle(
          color: AppColors.error,
          fontSize: 12,
          height: 1.25,
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          minimumSize: const Size.fromHeight(52),
          backgroundColor: AppColors.espresso,
          foregroundColor: AppColors.white,
          disabledBackgroundColor: const Color(0xFFAAA4A1),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(10),
          ),
          textStyle: const TextStyle(
            fontSize: 15,
            fontWeight: FontWeight.w700,
            letterSpacing: 0.2,
          ),
        ),
      ),
      progressIndicatorTheme: const ProgressIndicatorThemeData(
        color: AppColors.terracotta,
      ),
    );
  }
}
