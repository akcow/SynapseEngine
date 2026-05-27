import numpy as np
import random

class CollectionIndex:
    """A lightweight, zero-dependency HNSW (Hierarchical Navigable Small World) index implemented in pure Python/NumPy."""
    def __init__(self, dim: int = 128, M: int = 8, M_max: int = 12, efConstruction: int = 16, efSearch: int = 16) -> None:
        self.dim = dim
        self.M = M
        self.M_max = M_max
        self.efConstruction = efConstruction
        self.efSearch = efSearch
        
        # 概率因子：1 / ln(M) 决定节点向上升级的概率
        self.mL = 1.0 / np.log(M)
        
        self.nodes: dict[int, np.ndarray] = {}  # doc_id -> normalized vector
        self.levels: dict[int, int] = {}        # doc_id -> max level
        self.graphs: list[dict[int, list[int]]] = []  # Index l contains adjacency list for level l: doc_id -> list of doc_ids
        
        self.enter_point: int = None            # Current global entry point doc_id
        self.max_level: int = -1                # Maximum level of the graph
        
    def _distance(self, v1: np.ndarray, v2: np.ndarray) -> float:
        # 余弦距离 = 1.0 - 余弦相似度 (输入已归一化的向量，所以余弦相似度就是点积)
        return 1.0 - float(np.dot(v1, v2))

    def add(self, doc_id: int, vector: list[float]) -> None:
        v = np.array(vector, dtype='float32')
        norm = np.linalg.norm(v)
        if norm > 0:
            v = v / norm
        self.nodes[doc_id] = v
        
        # 决定该节点的层数 (概率生成)
        level = int(np.floor(-np.log(random.random()) * self.mL))
        self.levels[doc_id] = level
        
        # 扩建图层
        while len(self.graphs) <= level:
            self.graphs.append({})
            
        curr_ep = self.enter_point
        # 1. 查找插入的起始入口 (从最顶层向下贪心搜索，直到 level + 1 层)
        if curr_ep is not None:
            for l in range(self.max_level, level, -1):
                curr_ep = self._search_layer_greedy(v, curr_ep, l)
                
        # 2. 从 level 层向下到 0 层，建立双向连接
        start_level = min(level, self.max_level) if self.max_level >= 0 else -1
        ep_set = [curr_ep] if curr_ep is not None else []
        
        for l in range(start_level, -1, -1):
            # 在 l 层使用束搜索找到 efConstruction 个候选节点
            candidates = self._search_layer_beam(v, ep_set, self.efConstruction, l)
            # 选择最近的 M 个邻居
            candidates.sort(key=lambda x: x[0])
            neighbors = [node_id for _, node_id in candidates[:self.M]]
            
            # 建立双向边
            self.graphs[l][doc_id] = neighbors
            for n in neighbors:
                if n not in self.graphs[l]:
                    self.graphs[l][n] = []
                self.graphs[l][n].append(doc_id)
                # 裁剪超限的邻边
                if len(self.graphs[l][n]) > self.M_max:
                    self.graphs[l][n].sort(key=lambda x: self._distance(self.nodes[n], self.nodes[x]))
                    self.graphs[l][n] = self.graphs[l][n][:self.M_max]
            
            # 作为下一层的入口候选集
            ep_set = [node_id for _, node_id in candidates]
            
        # 如果新节点的层级大于当前最大层级，升级全局最大层级与入口点
        if level > self.max_level:
            self.max_level = level
            self.enter_point = doc_id
        elif self.enter_point is None:
            self.enter_point = doc_id
            self.max_level = level

    def _search_layer_greedy(self, qv: np.ndarray, ep: int, level: int) -> int:
        curr = ep
        curr_dist = self._distance(qv, self.nodes[curr])
        changed = True
        while changed:
            changed = False
            neighbors = self.graphs[level].get(curr, [])
            for n in neighbors:
                d = self._distance(qv, self.nodes[n])
                if d < curr_dist:
                    curr_dist = d
                    curr = n
                    changed = True
        return curr

    def _search_layer_beam(self, qv: np.ndarray, ep_set: list[int], ef: int, level: int) -> list[tuple[float, int]]:
        visited = set(ep_set)
        candidates = [(self._distance(qv, self.nodes[x]), x) for x in ep_set]
        result = list(candidates)
        
        while candidates:
            candidates.sort(key=lambda x: x[0])
            curr_dist, curr = candidates.pop(0)
            
            result.sort(key=lambda x: x[0])
            if curr_dist > result[-1][0]:
                break
                
            neighbors = self.graphs[level].get(curr, [])
            for n in neighbors:
                if n not in visited:
                    visited.add(n)
                    d = self._distance(qv, self.nodes[n])
                    result.sort(key=lambda x: x[0])
                    if d < result[-1][0] or len(result) < ef:
                        candidates.append((d, n))
                        result.append((d, n))
                        result.sort(key=lambda x: x[0])
                        result = result[:ef]
        return result

    def search(self, query_vector: list[float], top_k: int = 5) -> list[tuple[float, int]]:
        if not self.nodes or self.enter_point is None:
            return []
            
        qv = np.array(query_vector, dtype='float32')
        norm = np.linalg.norm(qv)
        if norm > 0:
            qv = qv / norm
            
        curr_ep = self.enter_point
        # 1. 贪心搜索下降到第 0 层
        for l in range(self.max_level, 0, -1):
            curr_ep = self._search_layer_greedy(qv, curr_ep, l)
            
        # 2. 在第 0 层做束搜索
        candidates = self._search_layer_beam(qv, [curr_ep], self.efSearch, 0)
        candidates.sort(key=lambda x: x[0])
        
        # 3. 还原为余弦相似度分数 (1.0 - 余弦距离) 并截取 top_k
        return [(1.0 - d, doc_id) for d, doc_id in candidates[:top_k]]

