# """Read-only P2 identity endpoint: exact root, HTML/JSON, standard library only."""

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .config.settings import Settings, load_settings
from .request.header.validate import negotiate_content_type
from .request.rejected import RequestRejected
from .request.validate import (
    validate_headers,
    validate_method,
    validate_no_body,
    validate_target,
)
from .response.page import CONTENT_SECURITY_POLICY, STYLESHEET, render_html

SOCKET_TIMEOUT_SECONDS = 5


class ApplicationHandler(BaseHTTPRequestHandler):
    """Handler for the HTTP server, with settings and response type."""
    settings: Settings
    response_type: str
    timeout = SOCKET_TIMEOUT_SECONDS
    server_version = "iot-identity"
    sys_version = ""

    @property
    def app_name(self) -> str:
        return self.settings.app_name

    @property
    def podname(self) -> str:
        return self.settings.podname

    @property
    def app_version(self) -> str:
        return self.settings.app_version

    def parse_request(self) -> bool:
        """
        Valider la requête HTTP et déterminer le type de réponse.
        Retourne True si la requête est valide et que le traitement peut continuer."""
        if not super().parse_request():
            return False

        self.close_connection = True
        try:
            validate_target(self.requestline)
            validate_headers(self.headers, self.request_version)
            validate_method(self.command)
            validate_no_body(self.headers)

            if self.command in {"GET", "HEAD"} and self.path == "/":
                accept_values = self.headers.get_all("Accept")
                accept = (
                    ",".join(accept_values)
                    if accept_values is not None
                    else None
                )
                self.response_type = negotiate_content_type(accept)
        except RequestRejected as error:
            self.send_error(error.status, str(error))
            return False

        return True

    def do_GET(self) -> None:
        """
        Répondre à la requête GET avec le type de contenu négocié.
        Si la requête est pour /css/stylesheet.css, renvoyer le CSS.
        """
        if self.path == "/css/stylesheet.css":
            self.reply(HTTPStatus.OK, STYLESHEET, "text/css; charset=utf-8")
            return

        if self.response_type == "application/json":
            payload = {"app": self.app_name, "pod": self.podname, "version": self.app_version}
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        else:
            body = render_html(self.settings, method=self.command, path=self.path, status=HTTPStatus.OK)

        self.reply(HTTPStatus.OK, body, f"{self.response_type}; charset=utf-8")

    def do_HEAD(self) -> None:
        # Même réponse que GET ; reply() enverra uniquement les en-têtes.
        self.do_GET()

    def send_error(self, code: int, message: str | None=None, explain: str | None=None) -> None:
        # status = HTTPStatus(code)
        # text = f"{status.value} {status.phrase}\n{message or status.description}\n"
        # self.reply(status, text.encode("utf-8"), "text/plain; charset=utf-8")
        """Transmettre l'erreur au template et envoyer son véritable statut."""

        status = HTTPStatus(code)

        body = render_html(
            self.settings,
            method=getattr(self, "command", None) or "unavailable",
            path=getattr(self, "path", None) or "unavailable",
            status=status,
            error_message=message or status.description,
            error_explanation=explain or "",
        )

        self.reply(
            status,
            body,
            "text/html; charset=utf-8",
        )

    def reply(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
        """Centraliser l’envoi et les en-têtes communs, y compris les erreurs."""
        body_allowed = status >= 200 and status not in {
            HTTPStatus.NO_CONTENT,
            HTTPStatus.RESET_CONTENT,
            HTTPStatus.NOT_MODIFIED,
        }

        headers = {
            "Content-Type": content_type,
            "X-App-Name": self.app_name,
            "Content-Security-Policy": CONTENT_SECURITY_POLICY,
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "Cache-Control": "no-store",
            "Vary": "Accept",
            "Connection": "close",
        }

        if body_allowed:
            headers["Content-Length"] = str(len(body))
        if status == HTTPStatus.METHOD_NOT_ALLOWED:
            headers["Allow"] = "GET, HEAD"

        self.close_connection = True
        try:
            self.send_response(status)
            for name, value in headers.items():
                self.send_header(name, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass  # Le client est parti : on ne peut plus terminer la réponse.

    def version_string(self) -> str:
        return self.server_version


def main() -> None:
    settings = load_settings()
    ApplicationHandler.settings = settings

    with ThreadingHTTPServer(("0.0.0.0", settings.port), ApplicationHandler) as server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nArrêt du serveur.")

if __name__ == "__main__":
    main()
