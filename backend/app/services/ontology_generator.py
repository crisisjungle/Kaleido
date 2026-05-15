class OntologyGenerator:
    def generate(self, document_texts=None, simulation_requirement="", additional_context=None):
        return {
            "entity_types": [
                {"name": "Region", "description": "地理或生态区域"},
                {"name": "Actor", "description": "参与推演的主体"},
                {"name": "Risk", "description": "风险或影响链路"},
            ],
            "edge_types": [
                {"name": "AFFECTS", "description": "影响关系"},
                {"name": "LOCATED_IN", "description": "空间归属"},
            ],
            "analysis_summary": simulation_requirement or "已生成默认本体。",
        }
