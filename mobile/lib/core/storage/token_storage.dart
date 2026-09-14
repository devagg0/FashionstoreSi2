abstract interface class TokenStorage {
  Future<void> saveToken(String token);

  Future<String?> getToken();

  Future<void> deleteToken();
}
