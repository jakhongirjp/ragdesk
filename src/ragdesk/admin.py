"""Operator CLI: ragdesk-admin create-key --tenant acme --name ci --scopes read,ingest"""

from __future__ import annotations

import argparse
import asyncio
import sys

from ragdesk.adapters.postgres import PostgresKeyStore, create_pool, migrate
from ragdesk.config import Settings
from ragdesk.domain.models import Scope


async def _run(args: argparse.Namespace) -> int:
    s = Settings()
    if s.database_url is None:
        print("RAGDESK_DATABASE_URL is required", file=sys.stderr)
        return 2
    pool = await create_pool(s.database_url, max_size=2)
    try:
        await migrate(pool, s.embedding_dimensions)
        keys = PostgresKeyStore(pool)
        if args.command == "create-key":
            scopes = frozenset(Scope(x) for x in args.scopes.split(","))
            print(await keys.create(args.tenant, args.name, scopes))
        elif args.command == "revoke-key":
            if not await keys.revoke(args.key_id):
                print("no active key with that id", file=sys.stderr)
                return 1
            print("revoked")
    finally:
        await pool.close()
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="ragdesk-admin")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create-key", help="create an API key; the secret is shown once")
    create.add_argument("--tenant", required=True)
    create.add_argument("--name", required=True)
    create.add_argument("--scopes", default="read")
    revoke = sub.add_parser("revoke-key")
    revoke.add_argument("key_id")
    sys.exit(asyncio.run(_run(parser.parse_args())))
