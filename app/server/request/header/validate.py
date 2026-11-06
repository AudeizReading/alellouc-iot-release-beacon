"""Validation des en-têtes HTTP, en particulier Accept et Host.
Le module http.client de Python ne valide pas les en-têtes, il les analyse simplement.
Le module http.server de Python valide la ligne de requête, mais pas les en-têtes.
Les autres fonctions décomposent la syntaxe Accept et ses valeurs entre guillemets.
"""

import re
from http import HTTPStatus

from ..rejected import RequestRejected
from .media_range import MediaRange

SUPPORTED_TYPES = ("text/html", "application/json")  # HTML gagne en cas d’égalité.
MAX_ACCEPT_LENGTH = 4096
MAX_ACCEPT_RANGES = 16

# Grammaires HTTP : un token, une valeur entre guillemets et un poids q.
TOKEN = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+")
QUOTED_VALUE = re.compile(r'"(?:[\t\x20\x21\x23-\x5b\x5d-\x7e]|\\[\t\x20-\x7e])*"')
QUALITY = re.compile(r"(?:0(?:\.[0-9]{0,3})?|1(?:\.0{0,3})?)")

def negotiate_content_type(accept: str | None) -> str:
    """Retenir le format acceptable de poids maximal ; HTML départage les égaux.
    Si aucun format n’est acceptable, lever RequestRejected(406).

    Exemple : Accept: text/html;q=0.8, application/json;q=0.9
    Exemple : Accept: text/html;q=0,*/*;q=1 interdit HTML mais autorise JSON.
    """
    if accept is None:
        return SUPPORTED_TYPES[0]
    if len(accept) > MAX_ACCEPT_LENGTH:
        raise RequestRejected(
            HTTPStatus.REQUEST_HEADER_FIELDS_TOO_LARGE, "Accept header too large."
        )

    entries = [entry for entry in split_quoted(accept, ",") if entry]
    if len(entries) > MAX_ACCEPT_RANGES:
        raise RequestRejected(
            HTTPStatus.REQUEST_HEADER_FIELDS_TOO_LARGE, "Too many Accept ranges."
        )

    ranges = [parse_media_range(entry) for entry in entries]
    reject_conflicting_ranges(ranges)
    selected = ""
    best_quality = 0

    for content_type in SUPPORTED_TYPES:
        matches = [item for item in ranges if item.matches(content_type)]
        if not matches:
            continue

        most_specific = max(matches, key=lambda item: item.specificity)
        if most_specific.quality > best_quality:
            selected = content_type
            best_quality = most_specific.quality

    if not selected:
        raise RequestRejected(
            HTTPStatus.NOT_ACCEPTABLE,
            "Available representations: text/html, application/json.",
        )
    return selected


def parse_media_range(value: str) -> MediaRange:
    """Découper un type de contenu avec paramètres et poids q.
    Exemple : Accept: text/html;charset=utf-8;q=0.8
    """
    media, *raw_parameters = split_quoted(value, ";")
    major, separator, minor = media.lower().partition("/")
    if not separator or not TOKEN.fullmatch(major) or not TOKEN.fullmatch(minor):
        raise RequestRejected(HTTPStatus.BAD_REQUEST, "Malformed Accept media range.")
    if major == "*" and minor != "*":
        raise RequestRejected(HTTPStatus.BAD_REQUEST, "Invalid Accept wildcard.")

    parameters: dict[str, str] = {}
    quality = 1000
    seen_quality = False

    for raw in raw_parameters:
        name, parameter = parse_parameter(raw)
        if seen_quality or name in parameters:
            raise RequestRejected(
                HTTPStatus.BAD_REQUEST,
                "Duplicate parameter or misplaced Accept weight.",
            )
        if name == "q":
            quality = parse_quality(parameter)
            seen_quality = True
        else:
            parameters[name] = parameter.lower() if name == "charset" else parameter

    return MediaRange(major, minor, tuple(sorted(parameters.items())), quality)


def parse_quality(value: str) -> int:
    """Convertir un poids q en millièmes, par exemple 0.8 devient 800.
    Le poids q doit être compris entre 0 et 1, avec au maximum 3 décimales.
    """
    if not QUALITY.fullmatch(value):
        raise RequestRejected(
            HTTPStatus.BAD_REQUEST,
            "Accept q must be between 0 and 1, with at most 3 decimals.",
        )
    whole, _, fraction = value.partition(".")
    return int(whole) * 1000 + int(fraction.ljust(3, "0"))


def reject_conflicting_ranges(ranges: list[MediaRange]) -> None:
    """Vérifier qu’aucune préférence n’a deux poids différents.
    Politique locale : une même préférence ne peut pas porter deux poids.
    """
    seen = {}
    for item in ranges:
        key = (item.major, item.minor, item.parameters)
        if key in seen and seen[key] != item.quality:
            raise RequestRejected(HTTPStatus.BAD_REQUEST, "Conflicting Accept ranges.")
        seen[key] = item.quality


def parse_parameter(value: str) -> tuple[str, str]:
    """Découper un paramètre de type name=value, avec ou sans guillemets.
    Exemple : charset=utf-8 ou charset="utf-8"
    """
    name, separator, raw = value.partition("=")
    name = name.strip().lower()
    raw = raw.strip()
    if not separator or not TOKEN.fullmatch(name):
        raise RequestRejected(HTTPStatus.BAD_REQUEST, "Malformed Accept parameter.")

    if TOKEN.fullmatch(raw):
        return name, raw
    if name != "q" and QUOTED_VALUE.fullmatch(raw):
        return name, re.sub(r"\\(.)", r"\1", raw[1:-1])

    raise RequestRejected(HTTPStatus.BAD_REQUEST, "Malformed Accept parameter value.")


def split_quoted(value: str, separator: str) -> list[str]:
    """
    Découper la liste sans couper une virgule ou un ; entre guillemets.
    Exemple : text/html, application/json;q=0.9
    Exemple : text/html;charset="utf-8", application/json;q=0.9
    """
    result: list[str] = []
    start = 0
    quoted = False
    escaped = False

    for index, char in enumerate(value):
        if escaped:
            escaped = False
        elif quoted and char == "\\":
            escaped = True
        elif char == '"':
            quoted = not quoted
        elif char == separator and not quoted:
            result.append(value[start:index].strip())
            start = index + 1

    if quoted or escaped:
        raise RequestRejected(HTTPStatus.BAD_REQUEST, "Malformed Accept header.")

    result.append(value[start:].strip())
    return result
