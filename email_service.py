"""
email_service.py
----------------
Envoi d'emails transactionnels via l'API officielle Resend (https://resend.com/docs/api-reference/emails/send-email).

Ce module ne contient AUCUNE logique métier (ni mot de passe oublié, ni sessions) : il sait seulement
envoyer un email et dire honnêtement si le fournisseur l'a accepté.

Configuration (variables d'environnement, jamais de valeur réelle dans le dépôt) :
  RESEND_API_KEY   clé API Resend (re_...). Si absente : le service est « non configuré ».
  EMAIL_FROM       expéditeur, ex. « Bitsure <no-reply@votre-domaine.tld> » (domaine vérifié chez Resend).
  EMAIL_REPLY_TO   (optionnel) adresse de réponse.

Garanties :
  - jamais de faux succès : `send_email` ne renvoie `ok=True` que si Resend a répondu 2xx avec un id ;
  - non configuré  -> EmailResult(ok=False, error_code="NOT_CONFIGURED") ;
  - refus / erreur réseau / timeout -> EmailResult(ok=False, ...) ;
  - la clé API et le contenu des emails ne sont jamais journalisés.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

import requests

logger = logging.getLogger("email_service")

RESEND_API_URL = "https://api.resend.com/emails"
DEFAULT_TIMEOUT_SECONDS = 10


@dataclass
class EmailResult:
    ok: bool
    provider_id: Optional[str] = None
    error_code: Optional[str] = None  # NOT_CONFIGURED | PROVIDER_REJECTED | NETWORK_ERROR | TIMEOUT | INVALID_REQUEST
    status_code: Optional[int] = None


def _api_key() -> str:
    return os.environ.get("RESEND_API_KEY", "").strip()


def _from_address() -> str:
    return os.environ.get("EMAIL_FROM", "").strip()


def is_configured() -> bool:
    return bool(_api_key() and _from_address())


def send_email(to: str, subject: str, html: str, text: str = "", idempotency_key: Optional[str] = None) -> EmailResult:
    api_key = _api_key()
    sender = _from_address()
    if not api_key or not sender:
        logger.warning("Resend non configuré (RESEND_API_KEY / EMAIL_FROM manquant) : email non envoyé.")
        return EmailResult(ok=False, error_code="NOT_CONFIGURED")
    if not to or "@" not in to or not subject:
        return EmailResult(ok=False, error_code="INVALID_REQUEST")

    payload = {"from": sender, "to": [to], "subject": subject, "html": html}
    if text:
        payload["text"] = text
    reply_to = os.environ.get("EMAIL_REPLY_TO", "").strip()
    if reply_to:
        payload["reply_to"] = reply_to

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key

    try:
        resp = requests.post(RESEND_API_URL, json=payload, headers=headers, timeout=DEFAULT_TIMEOUT_SECONDS)
    except requests.exceptions.Timeout:
        logger.error("Resend : délai dépassé.")
        return EmailResult(ok=False, error_code="TIMEOUT")
    except requests.exceptions.RequestException as exc:
        logger.error("Resend : erreur réseau (%s).", type(exc).__name__)
        return EmailResult(ok=False, error_code="NETWORK_ERROR")

    if 200 <= resp.status_code < 300:
        try:
            provider_id = (resp.json() or {}).get("id")
        except ValueError:
            provider_id = None
        if provider_id:
            return EmailResult(ok=True, provider_id=str(provider_id), status_code=resp.status_code)
        logger.error("Resend : réponse 2xx sans identifiant, envoi non confirmé.")
        return EmailResult(ok=False, error_code="PROVIDER_REJECTED", status_code=resp.status_code)

    # On journalise uniquement le statut, jamais le corps de la requête ni la clé.
    logger.error("Resend a refusé l'envoi (HTTP %s).", resp.status_code)
    return EmailResult(ok=False, error_code="PROVIDER_REJECTED", status_code=resp.status_code)


# ---------------------------------------------------------------------
# Templates Bitsure (couleurs reprises du design system : fond #080C0F, accent #20C997)
# ---------------------------------------------------------------------

def _escape(value: str) -> str:
    return (
        str(value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render_password_reset_email(reset_url: str, ttl_minutes: int, lang: str = "fr") -> tuple[str, str, str]:
    """Retourne (sujet, html, texte)."""
    url = _escape(reset_url)
    if lang == "en":
        subject = "Reset your Bitsure password"
        title = "Reset your password"
        intro = "We received a request to reset the password of your Bitsure account."
        cta = "Choose a new password"
        validity = f"This link is valid for {ttl_minutes} minutes and can only be used once."
        warning = (
            "If you did not make this request, you can ignore this email: your password will not change. "
            "Never share this link with anyone."
        )
        fallback = "If the button does not work, copy this link into your browser:"
        text = f"{title}\n\n{intro}\n\n{reset_url}\n\n{validity}\n{warning}\n"
    else:
        subject = "Réinitialisation de votre mot de passe Bitsure"
        title = "Réinitialiser votre mot de passe"
        intro = "Nous avons reçu une demande de réinitialisation du mot de passe de votre compte Bitsure."
        cta = "Choisir un nouveau mot de passe"
        validity = f"Ce lien est valable {ttl_minutes} minutes et ne peut être utilisé qu'une seule fois."
        warning = (
            "Si vous n'êtes pas à l'origine de cette demande, ignorez cet email : votre mot de passe ne sera pas modifié. "
            "Ne partagez ce lien avec personne."
        )
        fallback = "Si le bouton ne fonctionne pas, copiez ce lien dans votre navigateur :"
        text = f"{title}\n\n{intro}\n\n{reset_url}\n\n{validity}\n{warning}\n"

    html = f"""<!doctype html>
<html lang="{_escape(lang)}"><body style="margin:0;padding:0;background:#080C0F;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#080C0F;padding:32px 12px;">
<tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:480px;background:#0D1318;border:1px solid #1d2730;border-radius:12px;">
<tr><td style="padding:28px 28px 8px 28px;font-family:Arial,Helvetica,sans-serif;">
<div style="font-size:18px;font-weight:700;color:#20C997;letter-spacing:.5px;">Bitsure</div>
</td></tr>
<tr><td style="padding:8px 28px 0 28px;font-family:Arial,Helvetica,sans-serif;color:#E8EEF2;">
<h1 style="font-size:20px;margin:0 0 12px 0;">{_escape(title)}</h1>
<p style="font-size:14px;line-height:1.6;color:#B6C0C9;margin:0 0 20px 0;">{_escape(intro)}</p>
<p style="margin:0 0 20px 0;"><a href="{url}" style="display:inline-block;background:#20C997;color:#080C0F;text-decoration:none;font-weight:700;font-size:14px;padding:12px 22px;border-radius:8px;">{_escape(cta)}</a></p>
<p style="font-size:13px;line-height:1.6;color:#B6C0C9;margin:0 0 12px 0;">{_escape(validity)}</p>
<p style="font-size:12px;line-height:1.6;color:#8B98A4;margin:0 0 12px 0;">{_escape(fallback)}<br><span style="word-break:break-all;color:#8B98A4;">{url}</span></p>
<p style="font-size:12px;line-height:1.6;color:#F97066;margin:0 0 24px 0;">{_escape(warning)}</p>
</td></tr>
</table>
</td></tr></table>
</body></html>"""
    return subject, html, text


def render_password_changed_email(lang: str = "fr") -> tuple[str, str, str]:
    """Email d'information après un changement de mot de passe (sans lien ni secret)."""
    if lang == "en":
        subject = "Your Bitsure password was changed"
        body = (
            "The password of your Bitsure account was just changed and your other devices were signed out. "
            "If this was not you, reset your password immediately from the sign-in page and contact support."
        )
    else:
        subject = "Votre mot de passe Bitsure a été modifié"
        body = (
            "Le mot de passe de votre compte Bitsure vient d'être modifié et vos autres appareils ont été déconnectés. "
            "Si vous n'êtes pas à l'origine de ce changement, réinitialisez immédiatement votre mot de passe "
            "depuis la page de connexion et contactez le support."
        )
    html = f"""<!doctype html>
<html lang="{_escape(lang)}"><body style="margin:0;padding:0;background:#080C0F;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#080C0F;padding:32px 12px;">
<tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:480px;background:#0D1318;border:1px solid #1d2730;border-radius:12px;">
<tr><td style="padding:28px;font-family:Arial,Helvetica,sans-serif;">
<div style="font-size:18px;font-weight:700;color:#20C997;margin-bottom:12px;">Bitsure</div>
<h1 style="font-size:20px;margin:0 0 12px 0;color:#E8EEF2;">{_escape(subject)}</h1>
<p style="font-size:14px;line-height:1.6;color:#B6C0C9;margin:0;">{_escape(body)}</p>
</td></tr></table></td></tr></table></body></html>"""
    return subject, html, f"{subject}\n\n{body}\n"
