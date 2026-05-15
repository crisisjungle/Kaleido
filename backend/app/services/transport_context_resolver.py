class TransportContextResolver:
    def resolve(self, regions=None, diffusion_template=None, reference_time=None, preferred_provider=None, **kwargs):
        return {
            "provider": preferred_provider or "local_fallback",
            "diffusion_template": diffusion_template,
            "reference_time": reference_time,
            "transport_edges": [],
            "notes": [],
        }
