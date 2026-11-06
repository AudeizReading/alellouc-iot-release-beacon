"""Exception pour les requêtes rejetées."""

from http import HTTPStatus


class RequestRejected(Exception):
    """Une règle échoue : transporter son statut HTTP vers le handler."""

    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status = status
