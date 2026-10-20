"""Validation APIs for article delivery artifacts.

Project validation is loaded lazily so low-level rendering/style modules can import
delivery checks without creating a package initialization cycle.
"""

from .delivery import DeliveryValidation, validate_delivery_html

__all__ = [
    "ArticleProjectValidation",
    "DeliveryValidation",
    "validate_article_project",
    "validate_delivery_html",
]


def __getattr__(name: str):
    if name in {"ArticleProjectValidation", "validate_article_project"}:
        from .project import ArticleProjectValidation, validate_article_project

        return {
            "ArticleProjectValidation": ArticleProjectValidation,
            "validate_article_project": validate_article_project,
        }[name]
    raise AttributeError(name)
