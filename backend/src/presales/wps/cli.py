import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from presales.storage import database_factory

from .auth import PAIRING_LIFETIME_MINUTES, WpsAuth
from .diagnostics import WpsDiagnostics

ROOT = Path(__file__).resolve().parents[4]


def main():
    parser = argparse.ArgumentParser(description="签发 WPS 加载项一次性配对码")
    parser.add_argument("actor", help="售前人员姓名或公司账号")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("缺少 DATABASE_URL，请先完成项目初始化")
    factory = database_factory(database_url)
    with factory() as session:
        code = WpsAuth(session).issue_pairing(args.actor)
        session.commit()
    print(f"配对码（{PAIRING_LIFETIME_MINUTES} 分钟内单次有效）：{code}")


def purge_diagnostics():
    load_dotenv(ROOT / ".env")
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("缺少 DATABASE_URL，请先完成项目初始化")
    factory = database_factory(database_url)
    with factory() as session:
        purged = WpsDiagnostics(session).purge_expired()
        session.commit()
    print(f"已清理 {purged} 条超过 30 天的 WPS 诊断事件")
