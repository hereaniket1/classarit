"""Minimal API telemetry for the executive dashboard."""

import asyncio
import logging
from datetime import datetime, timezone
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from ..auth.database import auth_engine, schema_name

logger = logging.getLogger(__name__)


def _insert_metric(method, path, route_template, status_code, latency_ms, user_id):
    try:
        with auth_engine().begin() as conn:
            conn.execute(
                text(
                    f"""INSERT INTO {schema_name()}.api_request_metrics
                    (method,path,route_template,status_code,latency_ms,user_id)
                    VALUES (:method,:path,:route,:status,:latency,:user)"""
                ),
                {
                    "method": method[:10],
                    "path": path[:300],
                    "route": route_template[:300],
                    "status": int(status_code),
                    "latency": int(min(max(latency_ms, 0), 600000)),
                    "user": user_id,
                },
            )
            conn.execute(
                text(f"DELETE FROM {schema_name()}.api_request_metrics WHERE captured_at < CURRENT_TIMESTAMP - interval '30 days'")
            )
    except Exception:
        logger.debug("API telemetry unavailable; metric skipped")


async def record_api_metric(method, path, route_template, status_code, latency_ms, user_id=None):
    await asyncio.to_thread(_insert_metric, method, path, route_template, status_code, latency_ms, user_id)


def executive_metrics():
    with auth_engine().connect() as conn:
        daily = [
            dict(row)
            for row in conn.execute(
                text(
                    f"""SELECT date_trunc('day', captured_at)::date AS day,
                              count(*) AS calls,
                              round(avg(latency_ms))::int AS avg_latency_ms,
                              max(latency_ms) AS max_latency_ms,
                              count(*) FILTER (WHERE status_code>=500) AS errors
                    FROM {schema_name()}.api_request_metrics
                    WHERE captured_at >= CURRENT_TIMESTAMP - interval '7 days'
                    GROUP BY 1 ORDER BY 1"""
                )
            ).mappings()
        ]
        routes = [
            dict(row)
            for row in conn.execute(
                text(
                    f"""SELECT route_template, count(*) AS calls,
                              round(avg(latency_ms))::int AS avg_latency_ms,
                              max(latency_ms) AS max_latency_ms
                    FROM {schema_name()}.api_request_metrics
                    WHERE captured_at >= CURRENT_TIMESTAMP - interval '7 days'
                    GROUP BY route_template ORDER BY avg(latency_ms) DESC, count(*) DESC LIMIT 8"""
                )
            ).mappings()
        ]
        totals = conn.execute(
            text(
                f"""SELECT count(*) AS calls,
                          round(avg(latency_ms))::int AS avg_latency_ms,
                          count(*) FILTER (WHERE status_code>=500) AS errors
                FROM {schema_name()}.api_request_metrics
                WHERE captured_at >= CURRENT_TIMESTAMP - interval '7 days'"""
            )
        ).mappings().first()
        return {"daily": daily, "routes": routes, "totals": dict(totals or {})}


def registration_stats():
    with auth_engine().connect() as conn:
        row = conn.execute(
            text(
                f"""SELECT
                    (SELECT count(*) FROM {schema_name()}.students WHERE status='ACTIVE') AS students,
                    (SELECT count(*) FROM {schema_name()}.workspaces WHERE status='ACTIVE' AND workspace_type='INDIVIDUAL') AS individual_workspaces,
                    (SELECT count(*) FROM {schema_name()}.workspaces WHERE status='ACTIVE' AND workspace_type='INSTITUTE') AS institute_workspaces,
                    (SELECT count(DISTINCT m.user_id)
                     FROM {schema_name()}.workspace_memberships m
                     JOIN {schema_name()}.membership_roles r ON r.workspace_id=m.workspace_id AND r.membership_id=m.id
                     WHERE m.status='ACTIVE' AND r.role='TEACHER') AS teachers,
                    (SELECT count(*) FROM {schema_name()}.app_users WHERE status='ACTIVE') AS active_users"""
            )
        ).mappings().first()
        return dict(row or {})
