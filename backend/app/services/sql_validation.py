"""Валідація згенерованих SQL-запитів через AST SQLGlot."""

from dataclasses import dataclass

import sqlglot
from sqlglot import exp

from app.models.types import ValidationResult
from app.services.schema_service import (
    allowed_columns,
    allowed_tables,
    is_large_table,
)


@dataclass
class ParsedSql:
    """Результат розбору SQL-запиту."""

    tables: list[str]
    columns: list[str]
    aliases: dict[str, str]
    virtual_sources: set[str]
    expression: exp.Expression


def sanitize_user_text(text: str) -> str:
    """Очищає та обмежує текст користувача."""

    return (
        text
        .replace("```", "")
        .replace("\x00", "")
    )[:4000]


def _find_forbidden_operation(
    expression: exp.Expression,
) -> str | None:
    """Повертає назву небезпечної операції, знайденої в AST."""

    for node in expression.walk():
        # INSERT, UPDATE, DELETE, COPY, MERGE та інші DML.
        if isinstance(node, exp.DML):
            return node.key.upper()

        # CREATE та інші DDL, що наслідують exp.DDL.
        if isinstance(node, exp.DDL):
            return node.key.upper()

        # DROP не наслідує exp.DDL у SQLGlot 26.1.3.
        if isinstance(node, exp.Drop):
            return "DROP"

        if isinstance(node, exp.Alter):
            return "ALTER"

        if isinstance(node, exp.TruncateTable):
            return "TRUNCATE"

        # GRANT, REVOKE, CALL, EXEC та інші команди
        # можуть бути представлені як Command.
        if isinstance(node, exp.Command):
            return "COMMAND"

        # SELECT ... INTO створює таблицю і не є read-only.
        if isinstance(node, exp.Into):
            return "SELECT INTO"

        # SELECT FOR UPDATE / FOR SHARE встановлює блокування.
        if isinstance(node, exp.Query) and node.args.get("locks"):
            return "LOCKING SELECT"

    return None


def _select_output_aliases(
    expression: exp.Expression,
) -> set[str]:
    """Повертає aliases, створені в SELECT-проєкціях."""

    aliases: set[str] = set()

    for select in expression.find_all(exp.Select):
        for projection in select.expressions:
            if isinstance(projection, exp.Alias):
                alias = projection.alias_or_name

                if alias:
                    aliases.add(alias)

    return aliases


def _virtual_sources(
    expression: exp.Expression,
) -> set[str]:
    """Повертає aliases CTE та вкладених SELECT-запитів."""

    sources: set[str] = set()

    for cte in expression.find_all(exp.CTE):
        alias = cte.alias_or_name

        if alias:
            sources.add(alias)

    for subquery in expression.find_all(exp.Subquery):
        alias = subquery.alias_or_name

        if alias:
            sources.add(alias)

    return sources


def parse_sql(sql: str) -> ParsedSql:
    """Розбирає один PostgreSQL-запит та збирає його метадані."""

    statements = sqlglot.parse(
        sql,
        read="postgres",
    )

    if len(statements) != 1:
        raise ValueError(
            "Only one SQL statement is allowed."
        )

    expression = statements[0]
    virtual_sources = _virtual_sources(expression)

    tables: list[str] = []
    aliases: dict[str, str] = {}

    for table in expression.find_all(exp.Table):
        table_name = table.name

        # CTE у FROM SQLGlot також може представити як Table,
        # але це не фізична таблиця БД.
        if table_name in virtual_sources:
            continue

        if table_name not in tables:
            tables.append(table_name)

        if table.alias:
            aliases[table.alias] = table_name

        aliases[table_name] = table_name

    columns: list[str] = []

    for column in expression.find_all(exp.Column):
        name = column.name
        qualifier = column.table

        columns.append(
            f"{qualifier}.{name}"
            if qualifier
            else name
        )

    return ParsedSql(
        expression=expression,
        tables=tables,
        columns=columns,
        aliases=aliases,
        virtual_sources=virtual_sources,
    )


def validate_sql(sql: str) -> ValidationResult:
    """Перевіряє, що SQL є одним безпечним read-only запитом."""

    errors: list[str] = []
    warnings: list[str] = []

    if not sql or not sql.strip():
        return ValidationResult(
            is_valid=False,
            errors=["SQL query is empty."],
        )

    try:
        parsed = parse_sql(sql)
    except Exception as exc:
        return ValidationResult(
            is_valid=False,
            errors=[f"SQL syntax error: {exc}"],
        )

    expression = parsed.expression
    normalized_sql = expression.sql(
        dialect="postgres"
    )

    # Дозволяємо SELECT, UNION, INTERSECT та EXCEPT.
    if not isinstance(expression, exp.Query):
        errors.append(
            "Only read-only SELECT queries are allowed."
        )

    forbidden_operation = _find_forbidden_operation(
        expression
    )

    if forbidden_operation:
        errors.append(
            f"Forbidden operation detected: "
            f"{forbidden_operation}. "
            "Only read-only SELECT queries are allowed."
        )

    referenced_tables = parsed.tables
    referenced_columns = parsed.columns
    output_aliases = _select_output_aliases(expression)

    for table in referenced_tables:
        if table not in allowed_tables():
            errors.append(
                f"Unknown table: {table}"
            )

    for column in expression.find_all(exp.Column):
        col_name = column.name
        qualifier = column.table

        if qualifier:
            # Колонка належить CTE або вкладеному SELECT.
            # Вихідні колонки такого джерела не належать
            # безпосередньо фізичній схемі.
            if qualifier in parsed.virtual_sources:
                continue

            real_table = parsed.aliases.get(qualifier)

            if not real_table:
                errors.append(
                    f"Unknown table alias: {qualifier}"
                )
                continue

            if (
                col_name != "*"
                and col_name not in allowed_columns(real_table)
            ):
                errors.append(
                    f"Unknown column: {qualifier}.{col_name} "
                    f"(resolved table {real_table})"
                )

            continue

        # Alias SELECT-виразу, наприклад:
        # COUNT(*) AS total ORDER BY total
        if col_name in output_aliases:
            continue

        if (
            referenced_tables
            and not any(
                col_name in allowed_columns(table)
                for table in referenced_tables
            )
        ):
            errors.append(
                f"Unknown column: {col_name}"
            )

    for table in referenced_tables:
        if (
            is_large_table(table)
            and expression.find(exp.Where) is None
        ):
            warnings.append(
                f"Large table {table} is referenced "
                "without a WHERE clause."
            )

    # Прибираємо дублікати, зберігаючи порядок
    errors = list(dict.fromkeys(errors))
    warnings = list(dict.fromkeys(warnings))

    return ValidationResult(
        is_valid=not errors,
        errors=errors,
        warnings=warnings,
        referenced_tables=referenced_tables,
        referenced_columns=referenced_columns,
        normalized_sql=normalized_sql,
    )
