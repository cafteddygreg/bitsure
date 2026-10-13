# Le serveur web importe ce module. Il pointe désormais vers le bundle le plus récent
# (web_frontend_bundle_data.py) : avant, il contenait un ancien frontend, d'où des
# fonctionnalités (période de backtest, état du moteur) absentes du site.
from web_frontend_bundle_data import EMBEDDED_FRONTEND  # noqa: F401
