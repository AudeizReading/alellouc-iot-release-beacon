"""Charger les fichiers frontend et rendre le template HTML."""

from html import escape
from http import HTTPStatus
from pathlib import Path
from string import Template
from urllib.parse import quote

from ..config.settings import Settings

# Conserver le chemin logique : les fichiers d’une ConfigMap sont des symlinks.
# resolve() suivrait ces liens et pourrait changer le répertoire de référence.
APP_DIRECTORY = Path(__file__).absolute().parents[2]
FRONTEND_DIRECTORY = APP_DIRECTORY / "appli"

HTML_PATH = FRONTEND_DIRECTORY / "index.html"
STYLESHEET_PATH = FRONTEND_DIRECTORY / "css" / "stylesheet.css"

HTML_PAGE = Template(HTML_PATH.read_text(encoding="utf-8"))
STYLESHEET = STYLESHEET_PATH.read_bytes()
FAVICON_COLORS: dict[str, dict[str, str]] = {
    "release-beacon": {
        "bg_dark": "#0d1110",
        "bg_light": "#f2f0e8",
        "wire_dark": "#89968f",
        "wire_light": "#59615c",
        "accent_dark": "#b7ff3c",
        "accent_light": "#3f7000",
    },
}

DEFAULT_FAVICON_COLORS = FAVICON_COLORS["release-beacon"]

CONTENT_SECURITY_POLICY = (
    "default-src 'none'; "
    "style-src 'self'; "
    "img-src data:; "
    "base-uri 'none'; "
    "form-action 'none'; "
    "frame-ancestors 'none'"
)


def render_html(
    settings: Settings,
    *,
    method: str,
    path: str,
    status: HTTPStatus,
    error_message: str = "",
    error_explanation: str = "",
) -> bytes:
    """Remplacer les données dynamiques après les avoir échappées."""
    html = HTML_PAGE.substitute(
        app=escape(settings.app_name),
        app_version=escape(settings.app_version),
        part=escape(settings.part.upper()),
        pod=escape(settings.podname),
        team=escape(settings.team),
        team_mail=escape(settings.team_mail),
        method=escape(method),
        path=escape(path),
        status_code=str(status.value),
        status_reason=escape(status.phrase),
        favicon=escape(
            render_favicon(settings.app_name),
            quote=True,
        ),
        error_hidden="" if error_message else "hidden",
        error_message=escape(error_message),
        error_explanation=escape(error_explanation),
    )
    return html.encode("utf-8")


def render_favicon(app_name: str) -> str:
    colors = FAVICON_COLORS.get(app_name, DEFAULT_FAVICON_COLORS)

    bg_dark = colors["bg_dark"]
    bg_light = colors["bg_light"]
    wire_dark = colors["wire_dark"]
    wire_light = colors["wire_light"]
    accent_dark = colors["accent_dark"]
    accent_light = colors["accent_light"]

    svg = f"""\
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" fill="none">
  <style>
    .tile {{
      fill: light-dark({bg_dark}, {bg_light});
    }}

    .wire {{
      stroke: light-dark({wire_dark}, {wire_light});
    }}

    .accent {{
      fill: light-dark({accent_dark}, {accent_light});
      stroke: light-dark({accent_dark}, {accent_light});
    }}
  </style>

  <rect class="tile" width="32" height="32" rx="8"/>

  <!-- cube filaire -->
  <path
    class="wire"
    d="M16 6 25 10.5 16 15 7 10.5 16 6Z
       M7 10.5V21.5
       M25 10.5V21.5
       M16 15V26
       M7 21.5 16 26 25 21.5"
    stroke-width="1.4"
    stroke-linejoin="round"
    stroke-linecap="round"
  />

  <!-- cube / noyau central -->
  <path
    class="accent"
    d="M16 12.4 19.2 14 16 15.6 12.8 14 16 12.4Z"
    stroke-width="1"
    stroke-linejoin="round"
  />
</svg>
"""
    return "data:image/svg+xml," + quote(svg, safe="")
