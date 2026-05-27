import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.models.db_models import Base

# 极简纯 Python 加载 .env 文件的函数
def load_dotenv():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(os.path.dirname(current_dir))
    env_path = os.path.join(root_dir, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ[k.strip()] = v.strip()

# 载入环境变量
load_dotenv()

# 从环境变量中读取，如果没有，则降级为 SQLite 作为 Fallback
SQLALCHEMY_DATABASE_URL = os.getenv(
    "DATABASE_URL", "sqlite:///./memory_engine.db"
)

# 根据不同的数据库类型创建 Engine (SQLite 需要 check_same_thread，Postgres 不需要)
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(SQLALCHEMY_DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    """初始化数据库，确保启用 pgvector 并创建所有表"""
    if not SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
        # 如果是 PostgreSQL，在创表前必须先激活 vector 扩展
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
    
    Base.metadata.create_all(bind=engine)

def get_db():
    """获取数据库 Session 的生成器"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

