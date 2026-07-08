import sqlglot
from sqlglot import exp

from app.models.types import RiskLevel, ValidationResult
from app.services.schema_service import is_large_table, is_sensitive_table

SENSITIVE_COLUMNS = {'email', 'full_name', 'rejection_reason'}


def _is_broad_star_projection(expr: exp.Expression) -> bool:
    """Detect SELECT * / SELECT table.* only in the output list.

    COUNT(*) is safe aggregate syntax and must not be treated as broad data exposure.
    The previous implementation counted the star inside COUNT(*) and incorrectly
    pushed normal aggregate questions to HIGH risk.
    """
    if not isinstance(expr, exp.Select):
        return False
    for projection in expr.expressions:
        # SELECT *
        if isinstance(projection, exp.Star):
            return True
        # SELECT users.*
        if isinstance(projection, exp.Column) and isinstance(projection.this, exp.Star):
            return True
    return False


def _has_aggregation(expr: exp.Expression) -> bool:
    """Return True for GROUP BY or aggregate functions such as COUNT/SUM/AVG."""
    if expr.find(exp.Group) is not None:
        return True
    aggregate_types = (exp.Count, exp.Sum, exp.Avg, exp.Min, exp.Max)
    return any(expr.find(t) is not None for t in aggregate_types)


def assess_risk(sql: str, validation: ValidationResult) -> tuple[RiskLevel, str]:
    reasons: list[str] = []
    if not validation.is_valid:
        return RiskLevel.HIGH, 'Invalid SQL is treated as high risk and must not execute.'

    try:
        expr = sqlglot.parse_one(sql, read='postgres')
    except Exception:
        return RiskLevel.HIGH, 'SQL cannot be parsed during risk assessment.'

    has_where = expr.find(exp.Where) is not None
    has_limit = expr.find(exp.Limit) is not None
    has_broad_star = _is_broad_star_projection(expr)
    has_aggregation = _has_aggregation(expr)
    join_count = len(list(expr.find_all(exp.Join)))
    subquery_count = len(list(expr.find_all(exp.Subquery)))
    referenced_tables = validation.referenced_tables
    large_tables = [t for t in referenced_tables if is_large_table(t)]
    sensitive_tables = [t for t in referenced_tables if is_sensitive_table(t)]

    column_names = {col.split('.')[-1] for col in validation.referenced_columns}
    sensitive_cols = sorted(column_names & SENSITIVE_COLUMNS)

    score = 0

    # Expensive scan risk.
    if large_tables and not has_where:
        score += 3
        reasons.append(f'large table without WHERE: {", ".join(large_tables)}')

    # Data exposure risk. COUNT(*) must not trigger this; only actual SELECT * does.
    if has_broad_star:
        score += 2
        reasons.append('SELECT * returns broad data')

    # Row-returning queries need LIMIT. Aggregates/GROUP BY normally return a bounded summary.
    if not has_limit and not has_aggregation:
        score += 2
        reasons.append('no LIMIT on row-returning result')

    # Sensitive tables are not automatically HIGH when the query only returns aggregate metrics.
    if sensitive_tables and (has_broad_star or sensitive_cols):
        score += 2
        reasons.append(f'sensitive data touched: {", ".join(sensitive_tables)}')

    if sensitive_cols:
        score += 1
        reasons.append(f'sensitive columns selected/referenced: {", ".join(sensitive_cols)}')

    if join_count >= 2:
        score += 1
        reasons.append('multiple joins may be expensive')

    if subquery_count > 0:
        score += 1
        reasons.append('contains subquery')

    # Warnings from validation, for example large table without WHERE, should affect risk.
    # Avoid double-counting a large-table warning when it was already scored above.
    extra_warnings = [w for w in validation.warnings if w not in reasons]

    if score >= 4:
        return RiskLevel.HIGH, '; '.join(reasons + extra_warnings) or 'High-risk query by heuristic score.'
    if score >= 2 or extra_warnings:
        return RiskLevel.MEDIUM, '; '.join(reasons + extra_warnings) or 'Moderate-risk bounded query.'
    return RiskLevel.LOW, 'Narrow read-only query with bounded scope and no obvious sensitive broad scan.'
