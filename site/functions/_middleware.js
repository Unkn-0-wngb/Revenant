const BLOCKED_PATH_PREFIXES = ['/.git', '/.env', '/actuator/', '/debug/', '/wp-admin', '/wp-login', '/cgi-bin/'];
const BLOCKED_PATH_EXACT = new Set(['/env', '/manage/env', '/magento_version', '/xmlrpc.php', '/server-status']);
const BLOCKED_PATH_CONTAINS = ['phpinfo', 'wp-config', 'phpmyadmin'];
const BLOCKED_PATH_SUFFIXES = [
  '.bash_history', '.zsh_history', '.sh_history', '.fish_history',
  '.python_history', '.node_repl_history', '.irb_history', '.pry_history',
  '.sql', '.bak', '.php',
];

function isBlockedPath(pathname) {
  let p = pathname;
  try { p = decodeURIComponent(pathname); } catch (e) { return true; }
  p = p.toLowerCase().replace(/\/{2,}/g, '/');
  if (BLOCKED_PATH_PREFIXES.some((x) => p.startsWith(x))) return true;
  if (BLOCKED_PATH_EXACT.has(p)) return true;
  if (BLOCKED_PATH_CONTAINS.some((x) => p.includes(x))) return true;
  if (BLOCKED_PATH_SUFFIXES.some((x) => p.endsWith(x))) return true;
  return false;
}

export async function onRequest(context) {
  const url = new URL(context.request.url);
  if (isBlockedPath(url.pathname)) {
    return new Response('Forbidden', { status: 403, headers: { 'Cache-Control': 'no-store', 'X-Robots-Tag': 'noindex' } });
  }
  return context.next();
}
