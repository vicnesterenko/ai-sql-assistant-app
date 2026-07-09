from textwrap import dedent


def _comment(tables: str, why: str) -> str:
    return f"/*\nTables used: {tables}\nReason: {why}\n*/\n"


def delete_test_users_sql() -> str:
    return "DELETE FROM users WHERE is_test_account = true;"


def all_users_sql() -> str:
    return (
        _comment(
            tables="users",
            why="The user asked for all user rows; this will be routed as high risk.",
        )
        + "SELECT * FROM users;"
    )


def april_2025_new_users_by_channel_sql() -> str:
    return (
        _comment(
            tables="users",
            why="Count new user signups by acquisition channel for April 2025.",
        )
        + dedent(
            """
            SELECT
                acquisition_channel,
                COUNT(*) AS new_users
            FROM users
            WHERE created_at >= TIMESTAMPTZ '2025-04-01'
              AND created_at < TIMESTAMPTZ '2025-05-01'
              AND is_deleted = false
            GROUP BY acquisition_channel
            ORDER BY new_users DESC;
            """
        ).strip()
    )


def merchant_volume_last_quarter_sql() -> str:
    return (
        _comment(
            tables="transactions, users",
            why="Calculate merchant transaction volume while excluding internal test accounts.",
        )
        + dedent(
            """
            SELECT
                t.merchant_name,
                SUM(t.amount) AS transaction_volume,
                COUNT(*) AS transaction_count
            FROM transactions t
            JOIN users u ON u.id = t.user_id
            WHERE t.status = 'success'
              AND u.is_test_account = false
              AND u.is_deleted = false
              AND t.created_at >= date_trunc('quarter', CURRENT_DATE) - INTERVAL '3 months'
              AND t.created_at < date_trunc('quarter', CURRENT_DATE)
            GROUP BY t.merchant_name
            ORDER BY transaction_volume DESC
            LIMIT 20;
            """
        ).strip()
    )


def average_loan_approval_time_q1_sql() -> str:
    return (
        _comment(
            tables="loan_applications",
            why="Measure average time between submission and decision for applications submitted in Q1.",
        )
        + dedent(
            """
            SELECT
                ROUND(
                    AVG(EXTRACT(EPOCH FROM (decided_at - submitted_at)) / 3600.0),
                    2
                ) AS avg_approval_hours
            FROM loan_applications
            WHERE submitted_at >= TIMESTAMPTZ '2025-01-01'
              AND submitted_at < TIMESTAMPTZ '2025-04-01'
              AND decided_at IS NOT NULL
              AND status = 'approved';
            """
        ).strip()
    )


def users_after_january_first_sql() -> str:
    return (
        _comment(
            tables="users",
            why="Follow-up filter requested users signed up after January 1st.",
        )
        + dedent(
            """
            SELECT
                acquisition_channel,
                COUNT(*) AS new_users
            FROM users
            WHERE created_at >= TIMESTAMPTZ '2025-01-01'
              AND is_deleted = false
            GROUP BY acquisition_channel
            ORDER BY new_users DESC;
            """
        ).strip()
    )


def merchant_volume_q4_2024_sql() -> str:
    return (
        _comment(
            tables="transactions, users",
            why="Repeat previous merchant volume query for Q4 2024.",
        )
        + dedent(
            """
            SELECT
                t.merchant_name,
                SUM(t.amount) AS transaction_volume,
                COUNT(*) AS transaction_count
            FROM transactions t
            JOIN users u ON u.id = t.user_id
            WHERE t.status = 'success'
              AND u.is_test_account = false
              AND u.is_deleted = false
              AND t.created_at >= TIMESTAMPTZ '2024-10-01'
              AND t.created_at < TIMESTAMPTZ '2025-01-01'
            GROUP BY t.merchant_name
            ORDER BY transaction_volume DESC
            LIMIT 20;
            """
        ).strip()
    )


def signup_query_q4_2024_sql() -> str:
    return (
        _comment(
            tables="users",
            why="Repeat previous signup query for Q4 2024.",
        )
        + dedent(
            """
            SELECT
                acquisition_channel,
                COUNT(*) AS new_users
            FROM users
            WHERE created_at >= TIMESTAMPTZ '2024-10-01'
              AND created_at < TIMESTAMPTZ '2025-01-01'
              AND is_deleted = false
            GROUP BY acquisition_channel
            ORDER BY new_users DESC;
            """
        ).strip()
    )


def default_recent_users_sql() -> str:
    return (
        _comment(
            tables="users",
            why="Ambiguous user request; default to recent non-deleted users with a safe limit.",
        )
        + dedent(
            """
            SELECT
                id,
                acquisition_channel,
                created_at,
                is_test_account
            FROM users
            WHERE is_deleted = false
            ORDER BY created_at DESC
            LIMIT 100;
            """
        ).strip()
    )
