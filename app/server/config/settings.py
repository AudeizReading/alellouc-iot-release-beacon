"""Lire et valider l’environnement du processus Python."""

import os
import re
import socket
from dataclasses import dataclass

from .version import get_app_version

IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._@-]{0,63}")


@dataclass(frozen=True)
class Settings:
    """Nom de l’application, partie et port du serveur HTTP."""

    app_name: str
    app_version: str
    part: str
    port: int
    team: str  # Adresse e-mail du mainteneur, pour le pied de page.
    team_mail: str  # Adresse e-mail du mainteneur, pour le pied de page.
    podname: str  # Nom du pod, pour le pied de page.


def read_identifier(name: str) -> str:
    """Exiger une valeur explicite, courte, sans caractères de contrôle."""
    value = os.environ.get(name, "").strip()
    if not IDENTIFIER.fullmatch(value):
        raise ValueError(
            f"{name} is required: 1–64 ASCII letters, digits, dots, underscores "
            "or hyphens, starting with a letter or digit."
        )
    return value


def load_settings() -> Settings:
    """Lire et valider les variables d’environnement nécessaires."""
    app_name = read_identifier("APP_NAME")
    part = read_identifier("PART")
    port = int(os.environ.get("PORT", "8080"))
    team = read_identifier("IOT_LEADER_LOGIN")
    team_mail = read_identifier("MAINTENER_MAIL")
    podname = socket.gethostname()
    app_version = get_app_version()

    if not 1 <= port <= 65535:
        raise ValueError("PORT must be between 1 and 65535.")

    return Settings(
        app_name=app_name,
        app_version=app_version,
        part=part,
        port=port,
        team=team,
        podname=podname,
        team_mail=team_mail,
    )
