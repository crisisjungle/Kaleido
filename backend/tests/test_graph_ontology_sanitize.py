"""Bulletproofing: graph_builder.set_ontology must coerce every entity/edge
type name to Zep-valid ASCII before the Zep call, so no upstream ontology can
trigger the PascalCase 400 BadRequestError. Zep client is mocked (no network).
"""

from unittest.mock import MagicMock

from app.services.graph_builder import GraphBuilderService


def test_set_ontology_sanitizes_names_for_zep():
    svc = GraphBuilderService.__new__(GraphBuilderService)
    svc.client = MagicMock()
    svc._call_zep_with_retry = lambda func, desc: func()

    ontology = {
        "entity_types": [
            {"name": "host_population", "description": "x"},   # snake -> HostPopulation
            {"name": "病毒 Virus", "description": "y"},          # mixed  -> Virus
            {"name": "病毒", "description": "z"},                # pure CJK -> dropped
            {"name": "Region", "description": "r"},             # already valid
        ],
        "edge_types": [
            {"name": "transmits to", "description": "t",
             "source_targets": [{"source": "host_population", "target": "Region"}]},
        ],
    }

    svc.set_ontology("graph_x", ontology)

    call = svc.client.graph.set_ontology.call_args
    entities = call.kwargs["entities"]
    names = set(entities.keys())

    assert {"HostPopulation", "Virus", "Region"} <= names
    # pure-CJK entity dropped (un-convertible), nothing else leaks
    assert len(names) == 3
    # every name handed to Zep is ASCII alphanumeric (PascalCase-safe)
    assert all(n.isascii() and n.isalnum() for n in names)

    edges = call.kwargs["edges"]
    assert "TRANSMITS_TO" in edges
    _cls, source_targets = edges["TRANSMITS_TO"]
    # source/target references were sanitized to the valid entity names
    assert source_targets[0].source == "HostPopulation"
    assert source_targets[0].target == "Region"
