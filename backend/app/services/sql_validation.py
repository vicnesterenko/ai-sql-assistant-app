import re
from dataclasses import dataclass

import sqlglot
from sqlglot import exp

from app.models.types import ValidationResult
from app.services.schema_service import allowed_columns, allowed_tables, is_large_table

FORBIDDEN = {"INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE", "ALTER", "GRANT", "REVOKE", "EXEC", "CALL", "CREATE"}


@dataclass
class ParsedSql:
    expression: exp.Expression
    tables: list[str]
    columns: list[str]
    aliases: dict[str, str]


def sanitize_user_text(text: str) -> str:
    text = text.replace("```", "").replace("\x00", "")
    return text[:4000]


def _contains_forbidden(sql: str) -> str | None:
    tokens = set(re.findall(r"\b[A-Z_]+\b", sql.upper()))
    found = tokens & FORBIDDEN
    return sorted(found)[0] if found else None


def _select_output_aliases(expression: exp.Expression) -> set[str]:
    """Return aliases produced by the SELECT list.

    sqlglot represents ORDER BY aliases such as `ORDER BY new_users` as
    Column expressions. These are not real schema columns, so the schema
    validator must allow them when they were defined in the SELECT list,
    for example: `COUNT(*) AS new_users ORDER BY new_users DESC`.
    """
    aliases: set[str] = set()
    if isinstance(expression, exp.Select):
        for projection in expression.expressions:
            alias = projection.alias_or_name
            if isinstance(projection, exp.Alias) and alias:
                aliases.add(alias)
    return aliases


def parse_sql(sql: str) -> ParsedSql:
    statements = sqlglot.parse(sql, read="postgres")
    if len(statements) != 1:
        raise ValueError("Only one SQL statement is allowed")
    expression = statements[0]
    tables: list[str] = []
    aliases: dict[str, str] = {}
    for table in expression.find_all(exp.Table):
        table_name = table.name
        if table_name not in tables:
            tables.append(table_name)
        if table.alias:
            aliases[table.alias] = table_name
        aliases[table_name] = table_name
    columns: list[str] = []
    for column in expression.find_all(exp.Column):
        name = column.name
        qualifier = column.table
        columns.append(f"{qualifier}.{name}" if qualifier else name)
    return ParsedSql(expression=expression, tables=tables, columns=columns, aliases=aliases)


def validate_sql(sql: str) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    forbidden = _contains_forbidden(sql)
    if forbidden:
        return ValidationResult(
            is_valid=False,
            errors=[f"Forbidden operation detected: {forbidden}. Only read-only SELECT statements are allowed."],
        )

    try:
        parsed = parse_sql(sql)
    except Exception as exc:
        return ValidationResult(is_valid=False, errors=[f"SQL syntax error: {exc}"])

    expression = parsed.expression
    normalized_sql = expression.sql(dialect="postgres")
    output_aliases = _select_output_aliases(expression)

    if not isinstance(expression, exp.Select):
        errors.append("Only SELECT statements are allowed.")

    referenced_tables = parsed.tables
    referenced_columns = parsed.columns

    for table in referenced_tables:
        if table not in allowed_tables():
            errors.append(f"Unknown table: {table}")

    for column in expression.find_all(exp.Column):
        col_name = column.name
        qualifier = column.table
        if qualifier:
            real_table = parsed.aliases.get(qualifier)
            if not real_table:
                errors.append(f"Unknown table alias: {qualifier}")
                continue
            if col_name != "*" and col_name not in allowed_columns(real_table):
                errors.append(f"Unknown column: {qualifier}.{col_name} (resolved table {real_table})")
        else:
            if col_name in output_aliases:
                continue
            if referenced_tables and not any(col_name in allowed_columns(t) for t in referenced_tables):
                errors.append(f"Unknown column: {col_name}")

    for table in referenced_tables:
        if is_large_table(table) and expression.find(exp.Where) is None:
            warnings.append(f"Large table {table} is referenced without a WHERE clause.")

    return ValidationResult(
        is_valid=not errors,
        errors=errors,
        warnings=warnings,
        referenced_tables=referenced_tables,
        referenced_columns=referenced_columns,
        normalized_sql=normalized_sql,
    )
