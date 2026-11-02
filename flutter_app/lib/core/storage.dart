import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Small key/value store for the pairing data (server URL, tokens, device id, language).
abstract class KeyValueStore {
  Future<String?> read(String key);
  Future<void> write(String key, String? value);
}

/// Android Keystore-backed storage: tokens never land in plain SharedPreferences, logs or backups.
class SecureStore implements KeyValueStore {
  SecureStore() : _s = const FlutterSecureStorage();
  final FlutterSecureStorage _s;

  @override
  Future<String?> read(String key) => _s.read(key: key);

  @override
  Future<void> write(String key, String? value) =>
      value == null ? _s.delete(key: key) : _s.write(key: key, value: value);
}

/// In-memory store for tests.
class MemoryStore implements KeyValueStore {
  MemoryStore([Map<String, String>? initial]) : data = {...?initial};
  final Map<String, String> data;

  @override
  Future<String?> read(String key) async => data[key];

  @override
  Future<void> write(String key, String? value) async {
    if (value == null) {
      data.remove(key);
    } else {
      data[key] = value;
    }
  }
}
