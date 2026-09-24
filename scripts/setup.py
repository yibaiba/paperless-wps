import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
target = ROOT / ".env"
if target.exists():
    print(".env 已存在，保留现有配置")
else:
    password = secrets.token_urlsafe(32)
    content = (
        f"POSTGRES_PASSWORD={password}\n"
        f"DATABASE_URL=postgresql+psycopg://presales:{password}@127.0.0.1:25432/presales\n"
    )
    with target.open("x") as output:
        output.write(content)
    target.chmod(0o600)
    print("已生成本地数据库配置 .env")
