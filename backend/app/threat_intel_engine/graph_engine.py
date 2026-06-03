"""Graph-based botnet and coordination detection."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx

from app.threat_intel_engine.schemas import GraphEdge, GraphNode, ThreatGraphSnapshot


class ThreatGraphBuilder:
    """Build correlation graphs from co-occurrence and shared attributes."""

    def __init__(self) -> None:
        self._co_view: Dict[str, Dict[Tuple[str, str], int]] = defaultdict(
            lambda: defaultdict(int)
        )
        self._attrs: Dict[str, Dict[str, Dict[str, str]]] = defaultdict(dict)
        self._threat: Dict[str, Dict[str, float]] = defaultdict(dict)

    def link(
        self,
        stream_id: str,
        a: str,
        b: str,
        *,
        reason: str = "co_occurrence",
        weight: float = 1.0,
    ) -> None:
        if a == b:
            return
        key = tuple(sorted((a, b)))
        self._co_view[stream_id][key] += int(weight * 10)
        self._attrs[stream_id].setdefault(a, {})["last_reason"] = reason
        self._attrs[stream_id].setdefault(b, {})["last_reason"] = reason

    def set_node_meta(
        self,
        stream_id: str,
        node_id: str,
        *,
        label: str = "",
        platform: str = "",
        threat_score: float = 0.0,
        bot_probability: float = 0.0,
    ) -> None:
        self._attrs[stream_id][node_id] = {
            "label": label or node_id[:8],
            "platform": platform,
        }
        self._threat[stream_id][node_id] = {
            "threat_score": threat_score,
            "bot_probability": bot_probability,
        }

    def build_snapshot(self, stream_id: str) -> ThreatGraphSnapshot:
        edges_raw = self._co_view.get(stream_id, {})
        G = nx.Graph()
        for (a, b), w in edges_raw.items():
            if w >= 2:
                G.add_edge(a, b, weight=w)

        meta = self._attrs.get(stream_id, {})
        threat = self._threat.get(stream_id, {})
        for nid in set(meta.keys()) | set(threat.keys()):
            if not G.has_node(nid):
                G.add_node(nid)

        clusters: List[List[str]] = []
        coordination = 0.0
        community_count = 0
        modularity_score = 0.0
        high_centrality_nodes: List[str] = []
        if G.number_of_nodes() > 0:
            components = list(nx.connected_components(G))
            communities: List[Set[str]] = []
            if G.number_of_edges() > 0 and G.number_of_nodes() >= 3:
                try:
                    communities = [
                        set(c)
                        for c in nx.algorithms.community.greedy_modularity_communities(
                            G, weight="weight"
                        )
                    ]
                    community_count = len(communities)
                    if community_count > 1:
                        modularity_score = float(
                            nx.algorithms.community.modularity(
                                G, communities, weight="weight"
                            )
                        )
                except Exception:
                    communities = []
            bot_clusters = [
                sorted(c)
                for c in (communities or components)
                if len(c) >= 3
                and self._cluster_bot_score(c, threat) >= 0.45
            ]
            clusters = bot_clusters[:20]
            if components:
                largest = max(len(c) for c in components)
                coordination = min(
                    1.0,
                    (largest / max(G.number_of_nodes(), 1)) * 0.7
                    + (len(bot_clusters) / max(len(components), 1)) * 0.3,
                )
            if G.number_of_nodes() >= 3:
                centrality = nx.degree_centrality(G)
                high_centrality_nodes = [
                    n
                    for n, _ in sorted(
                        centrality.items(), key=lambda item: item[1], reverse=True
                    )[:12]
                    if centrality.get(n, 0.0) >= 0.25
                ]

        node_cluster: Dict[str, int] = {}
        for i, cl in enumerate(clusters):
            for n in cl:
                node_cluster[n] = i

        nodes: List[GraphNode] = []
        for nid in list(G.nodes())[:200]:
            m = meta.get(nid, {})
            t = threat.get(nid, {})
            nodes.append(
                GraphNode(
                    id=nid,
                    label=m.get("label", nid[:8]),
                    threat_score=t.get("threat_score", 0.0),
                    bot_probability=t.get("bot_probability", 0.0),
                    platform=m.get("platform"),
                    cluster_id=node_cluster.get(nid),
                )
            )

        edges: List[GraphEdge] = []
        for a, b, data in list(G.edges(data=True))[:400]:
            edges.append(
                GraphEdge(
                    source=a,
                    target=b,
                    weight=float(data.get("weight", 1)),
                    relation="correlated",
                )
            )

        return ThreatGraphSnapshot(
            stream_id=stream_id,
            nodes=nodes,
            edges=edges,
            bot_clusters=clusters,
            coordination_score=round(coordination, 4),
            community_count=community_count,
            modularity_score=round(max(0.0, modularity_score), 4),
            high_centrality_nodes=high_centrality_nodes,
        )

    def _cluster_bot_score(
        self, members: Set[str], threat: Dict[str, Dict[str, float]]
    ) -> float:
        if not members:
            return 0.0
        scores = [threat.get(m, {}).get("bot_probability", 0.0) for m in members]
        return sum(scores) / len(scores)

    def clear_stream(self, stream_id: str) -> None:
        self._co_view.pop(stream_id, None)
        self._attrs.pop(stream_id, None)
        self._threat.pop(stream_id, None)
