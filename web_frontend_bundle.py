# Auto-generated embedded frontend bundle (serves SPA even if dist/ is not built on Railway)
import base64
import gzip

from web_frontend_bundle_data import (
    INDEX_HTML_GZ_B64,
    ASSET_CSS_NAME,
    ASSET_CSS_GZ_B64,
    ASSET_JS_NAME,
    ASSET_JS_GZ_B64,
)

_CACHE = {}


def get_embedded_asset(path: str):
    if not _CACHE:
        _CACHE["/"] = (gzip.decompress(base64.b64decode(INDEX_HTML_GZ_B64)), "text/html; charset=utf-8")
        _CACHE["/index.html"] = _CACHE["/"]
        _CACHE[ASSET_CSS_NAME] = (gzip.decompress(base64.b64decode(ASSET_CSS_GZ_B64)), "text/css; charset=utf-8")
        _CACHE[ASSET_JS_NAME] = (gzip.decompress(base64.b64decode(ASSET_JS_GZ_B64)), "application/javascript; charset=utf-8")
    if path in _CACHE:
        return _CACHE[path]
    if not path.startswith("/api") and not path.startswith("/assets/"):
        return _CACHE["/"]
    return None
