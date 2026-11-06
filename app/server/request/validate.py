"""Contient des fonctions de validation pour les requêtes HTTP entrantes."""
from __future__ import annotations

import re
from email.message import Message
from http import HTTPStatus

from .rejected import RequestRejected

MAX_TARGET_LENGTH = 2048
MAX_HEADER_CHARACTERS = 8192
DISALLOWED_METHODS = {
    "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE", "CONNECT",
}
ALLOWED_TARGETS = {
    "/",
    "/css/stylesheet.css",
}

def validate_target(request_line: str) -> None:
    """Valider la cible de la requête HTTP.
    Vérifie la longueur, l’absence de chaînes de requête et de fragments,
    et que la cible est exactement /.
    Python a déjà validé la ligne, mais normalise // dans self.path.
    Examiner la cible reçue dans la ligne originale préserve la règle exacte.
    """
    target = request_line.split()[1]
    if len(target) > MAX_TARGET_LENGTH:
        raise RequestRejected(HTTPStatus.REQUEST_URI_TOO_LONG, "Request target too long.")

    if "?" in target or "#" in target:
        raise RequestRejected(
            HTTPStatus.BAD_REQUEST, "Query strings and fragments are not allowed."
        )

    if target not in ALLOWED_TARGETS:
        raise RequestRejected(
            HTTPStatus.NOT_FOUND,
            "Resource not found.",
        )


def validate_headers(headers: Message, http_version: str) -> None:
    """Valider les en-têtes HTTP.
    Vérifie la taille totale, l’absence d’en-têtes pliés et de défauts,
    et que l’en-tête Host est présent exactement une fois pour HTTP/1.1
    et qu’il n’est pas vide.
    """
    size = sum(len(name) + len(value) for name, value in headers.items())
    if size > MAX_HEADER_CHARACTERS:
        raise RequestRejected(
            HTTPStatus.REQUEST_HEADER_FIELDS_TOO_LARGE, "Headers too large."
        )

    folded = any("\r" in value or "\n" in value for value in headers.values())
    if headers.defects or folded:
        raise RequestRejected(HTTPStatus.BAD_REQUEST, "Malformed or folded headers.")

    hosts = headers.get_all("Host", [])
    if len(hosts) > 1 or (http_version == "HTTP/1.1" and not hosts):
        raise RequestRejected(HTTPStatus.BAD_REQUEST, "Expected one Host header.")

    if hosts and not hosts[0].strip():
        raise RequestRejected(HTTPStatus.BAD_REQUEST, "Host cannot be empty.")


def validate_method(method: str) -> None:
    """Valider la méthode HTTP.
    Seules GET et HEAD sont autorisées.
    Les méthodes inconnues seront rejetées avec 501 par BaseHTTPRequestHandler.
    """
    if method in DISALLOWED_METHODS:
        raise RequestRejected(
            HTTPStatus.METHOD_NOT_ALLOWED, "Only GET and HEAD are allowed."
        )

def validate_no_body(headers: Message) -> None:
    """Valider qu’il n’y a pas de corps de requête.
    Vérifie l’absence d’en-tête Transfer-Encoding, que Content-Length est absent ou zéro,
    et que l’en-tête Expect n’est pas présent.
    """
    if "Transfer-Encoding" in headers:
        raise RequestRejected(
            HTTPStatus.BAD_REQUEST,
            "Request bodies and Transfer-Encoding are not allowed.",
        )

    lengths = headers.get_all("Content-Length", [])
    if len(lengths) > 1:
        raise RequestRejected(HTTPStatus.BAD_REQUEST, "Duplicate Content-Length.")

    if lengths:
        length = lengths[0]
        is_digits = re.fullmatch(r"[0-9]+", length)
        is_zero = not length.strip("0")
        if not is_digits or not is_zero:
            raise RequestRejected(
                HTTPStatus.BAD_REQUEST, "Content-Length must be zero or absent."
            )

    if "Expect" in headers:
        raise RequestRejected(
            HTTPStatus.EXPECTATION_FAILED,
            "Request body expectations are not supported.",
        )
