"""Traversals and shortest paths on a graph written out in the question.

Edges are written ``A-B`` (undirected) or ``A->B`` (directed), separated by
commas or spaces; ``A-B:4`` or ``A-B (4)`` gives a weight. The start vertex is
taken from "from X" or "starting at X". Neighbours are visited in alphabetical
(or numeric) order, and the answer says so, because BFS and DFS orders depend
on that choice.

Supported: breadth-first search, depth-first search (recursive order), and
shortest paths (BFS when unweighted, Dijkstra when every weight is
non-negative). Graphs of up to 50 vertices.
"""

from __future__ import annotations

import heapq
import re
from collections import deque

from scholariq.answering.solvers.base import Solution, SolverError

MAX_VERTICES = 50
_EDGE = re.compile(
    r"(?<![\w>])(?P<u>[A-Za-z0-9]{1,3})\s*(?P<arrow>->|→|-|–|—)\s*(?P<v>[A-Za-z0-9]{1,3})(?![\w-])"
    r"(?:\s*(?::|\()\s*(?P<w>\d+(?:\.\d+)?)\)?)?"
)


def _key(v: str) -> tuple[int, int | str]:
    return (0, int(v)) if v.isdigit() else (1, v)


class GraphSolver:
    name = "graph"
    description = "BFS, DFS and shortest paths on a graph given as a list of edges"

    def solve(self, text: str) -> Solution | SolverError | None:
        low = text.lower()
        op = (
            "bfs"
            if re.search(r"\b(bfs|breadth[- ]first)\b", low)
            else "dfs"
            if re.search(r"\b(dfs|depth[- ]first)\b", low)
            else "path"
            if re.search(r"\bshortest (path|distance)", low)
            else None
        )
        if op is None or "edge" not in low and not re.search(r"\w\s*(->|-)\s*\w.*,", text):
            return None
        edges = [m.groupdict() for m in _EDGE.finditer(text)]
        if len(edges) < 1:
            return None
        directed = any(e["arrow"] in ("->", "→") for e in edges)
        weighted = any(e["w"] for e in edges)
        adj: dict[str, dict[str, float]] = {}
        for e in edges:
            w = float(e["w"]) if e["w"] else 1.0
            adj.setdefault(e["u"], {})[e["v"]] = w
            adj.setdefault(e["v"], {})
            if not directed:
                adj[e["v"]][e["u"]] = w
        if len(adj) > MAX_VERTICES:
            return SolverError(self.name, f"Graphs of up to {MAX_VERTICES} vertices are supported.")
        start_m = re.search(
            r"\b(?:from|starting (?:at|from)|start(?:ing)? vertex|source)\s+([A-Za-z0-9]{1,3})\b",
            text,
        )
        start = start_m.group(1) if start_m else min(adj, key=_key)
        if start not in adj:
            return SolverError(self.name, f"The start vertex {start} is not in the graph.")
        nbrs = {u: sorted(vs, key=_key) for u, vs in adj.items()}
        kind = "directed" if directed else "undirected"
        edge_note = (
            f"{len(edges)} edge(s), {len(adj)} vertices, {kind}{', weighted' if weighted else ''}."
        )
        assumption = "Neighbours are taken in alphabetical/numeric order."
        if op == "bfs":
            order, steps, seen, q = [], [], {start}, deque([start])
            while q:
                u = q.popleft()
                order.append(u)
                new = [v for v in nbrs[u] if v not in seen]
                seen.update(new)
                q.extend(new)
                steps.append(f"Visit {u}; queue {list(q) if q else 'empty'}.")
            return Solution(
                self.name,
                "Breadth-first search",
                "BFS order: " + ", ".join(order),
                steps=[edge_note, assumption, *steps],
                concept="ds.bfs",
                limitations=self._unreached(adj, order),
            )
        if op == "dfs":
            order, steps, seen = [], [], set()

            def visit(u: str, depth: int) -> None:
                seen.add(u)
                order.append(u)
                steps.append(f"{'  ' * depth}Visit {u}.")
                for v in nbrs[u]:
                    if v not in seen:
                        visit(v, depth + 1)

            visit(start, 0)
            return Solution(
                self.name,
                "Depth-first search",
                "DFS order: " + ", ".join(order),
                steps=[edge_note, assumption, *steps],
                concept="ds.dfs",
                limitations=self._unreached(adj, order),
            )
        target_m = re.search(r"\bto\s+([A-Za-z0-9]{1,3})\b", text)
        dist, prev = self._dijkstra(adj, start)
        rows = [
            [
                v,
                "unreachable" if v not in dist else f"{dist[v]:g}",
                self._path(prev, v) if v in dist else "-",
            ]
            for v in sorted(adj, key=_key)
        ]
        method = (
            "Dijkstra's algorithm (all weights are non-negative)"
            if weighted
            else "BFS (unweighted, each edge counts 1)"
        )
        if target_m and target_m.group(1) in adj:
            t = target_m.group(1)
            result = (
                f"Shortest {start} to {t}: {dist[t]:g} via {self._path(prev, t)}"
                if t in dist
                else f"{t} cannot be reached from {start}."
            )
        else:
            result = f"Shortest distances from {start} computed for {len(dist)} vertices."
        return Solution(
            self.name,
            "Shortest paths",
            result,
            steps=[edge_note, f"Method: {method}.", assumption],
            columns=["Vertex", "Distance", "Path"],
            rows=rows,
            concept="algo.dijkstra" if weighted else "ds.bfs",
        )

    @staticmethod
    def _unreached(adj: dict[str, dict[str, float]], order: list[str]) -> list[str]:
        missing = sorted(set(adj) - set(order), key=_key)
        return [f"Not reachable from the start: {', '.join(missing)}."] if missing else []

    @staticmethod
    def _dijkstra(
        adj: dict[str, dict[str, float]], s: str
    ) -> tuple[dict[str, float], dict[str, str]]:
        dist, prev, heap = {s: 0.0}, {}, [(0.0, _key(s), s)]
        done: set[str] = set()
        while heap:
            d, _, u = heapq.heappop(heap)
            if u in done:
                continue
            done.add(u)
            for v in sorted(adj[u], key=_key):
                nd = d + adj[u][v]
                if v not in dist or nd < dist[v]:
                    dist[v], prev[v] = nd, u
                    heapq.heappush(heap, (nd, _key(v), v))
        return dist, prev

    @staticmethod
    def _path(prev: dict[str, str], v: str) -> str:
        path = [v]
        while path[-1] in prev:
            path.append(prev[path[-1]])
        return " → ".join(reversed(path))
