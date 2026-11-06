"""Une préférence de type de contenu, par exemple text/html;charset=utf-8;q=0.8."""
from dataclasses import dataclass


@dataclass(frozen=True)
class MediaRange:
    """Une préférence, par exemple text/html;charset=utf-8;q=0.8."""

    major: str
    minor: str
    parameters: tuple[tuple[str, str], ...]
    quality: int  # Millièmes : 0.8 devient 800, sans calcul flottant.

    @property
    def specificity(self) -> tuple[int, int]:
        """Plus la préférence est précise, plus le tuple est grand."""
        exact_parts = int(self.major != "*") + int(self.minor != "*")
        return exact_parts, len(self.parameters)

    def matches(self, content_type: str) -> bool:
        """Vérifier si la préférence correspond à un type de contenu donné."""
        major, minor = content_type.split("/")
        if self.major not in ("*", major) or self.minor not in ("*", minor):
            return False

        return all(
            name == "charset" and value.lower() == "utf-8"
            for name, value in self.parameters
        )
