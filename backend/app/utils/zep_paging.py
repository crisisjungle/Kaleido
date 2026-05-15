def fetch_all_nodes(client, graph_id):
    graph = getattr(client, "graph", None)
    nodes_api = getattr(graph, "node", None) or getattr(graph, "nodes", None)
    if nodes_api and hasattr(nodes_api, "get_by_graph_id"):
        result = nodes_api.get_by_graph_id(graph_id=graph_id)
        return getattr(result, "nodes", result) or []
    return []


def fetch_all_edges(client, graph_id):
    graph = getattr(client, "graph", None)
    edges_api = getattr(graph, "edge", None) or getattr(graph, "edges", None)
    if edges_api and hasattr(edges_api, "get_by_graph_id"):
        result = edges_api.get_by_graph_id(graph_id=graph_id)
        return getattr(result, "edges", result) or []
    return []
