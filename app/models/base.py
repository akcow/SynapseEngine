from enum import Enum

class MemoryLevel(str, Enum):
    """记忆的层级，从具体碎片到抽象洞察"""
    EXPLICIT = "explicit"      # 显式事实
    DEDUCTIVE = "deductive"    # 演绎推论
    INDUCTIVE = "inductive"    # 归纳人格
    INSIGHT = "insight"        # 深度洞察

# 恢复 Engine 依赖的层级顺序定义
LEVEL_HIERARCHY = [
    MemoryLevel.EXPLICIT,
    MemoryLevel.DEDUCTIVE,
    MemoryLevel.INDUCTIVE,
    MemoryLevel.INSIGHT
]
