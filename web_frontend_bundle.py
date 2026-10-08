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
        css_bytes = (gzip.decompress(base64.b64decode(ASSET_CSS_GZ_B64)), "text/css; charset=utf-8")
        js_bytes = (gzip.decompress(base64.b64decode(ASSET_JS_GZ_B64)), "application/javascript; charset=utf-8")
        _CACHE[ASSET_CSS_NAME] = css_bytes
        _CACHE[f"/assets/{ASSET_CSS_NAME.lstrip('/')}"] = css_bytes
        _CACHE[ASSET_JS_NAME] = js_bytes
        _CACHE[f"/assets/{ASSET_JS_NAME.lstrip('/')}"] = js_bytes
        _CACHE["__css__"] = css_bytes
        _CACHE["__js__"] = js_bytes
    if path in _CACHE:
        return _CACHE[path]
    if path.startswith("/assets/"):
        if path.endswith(".css"):
            return _CACHE["__css__"]
        if path.endswith(".js") or path.endswith(".mjs"):
            return _CACHE["__js__"]
    if not path.startswith("/api") and not path.startswith("/assets/"):
        return _CACHE["/"]
    return None
