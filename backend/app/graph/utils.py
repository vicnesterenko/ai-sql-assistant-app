"""Допоміжні функції для роботи зі значеннями об’єктів."""


def obj_value(obj, key, default=None):
    """Повертає значення поля зі словника або об’єкта."""

    if obj is None:
        return default

    if isinstance(obj, dict):
        return obj.get(key, default)

    return getattr(obj, key, default)
