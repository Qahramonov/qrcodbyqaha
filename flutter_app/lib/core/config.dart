class AppInfo {
  static const name = 'Chat helper Control';
  static const version = '3.0.0';

  /// The backend runs on the same phone in Termux and listens on localhost only (see INSTALL_TERMUX.md).
  static const defaultServer = 'http://127.0.0.1:8787';
}

/// Hosts that may be reached over plain HTTP: the backend on this phone (Termux) or the emulator's host.
/// Everything else must use HTTPS — the same rule is enforced by res/xml/network_security_config.xml.
const localHosts = {'127.0.0.1', 'localhost', '10.0.2.2'};

/// Normalizes user input ("127.0.0.1:8787", "https://x.example/api/v1/") to a base URL without a trailing slash.
String normalizeServer(String input) {
  var s = input.trim();
  if (s.isEmpty) return s;
  if (!s.contains('://')) {
    final host = s.split(':').first.split('/').first;
    s = '${localHosts.contains(host) ? 'http' : 'https'}://$s';
  }
  s = s.replaceAll(RegExp(r'/+$'), '');
  if (s.endsWith('/api/v1')) s = s.substring(0, s.length - '/api/v1'.length);
  return s;
}

/// Returns a translation key describing what is wrong with [url], or null when it is acceptable.
String? validateServer(String url) {
  final uri = Uri.tryParse(url);
  if (uri == null || uri.host.isEmpty || !(uri.scheme == 'http' || uri.scheme == 'https')) return 'pair.err_url';
  if (uri.scheme == 'http' && !localHosts.contains(uri.host)) return 'pair.err_https';
  return null;
}
