class PublicDataGroundingService:
    def ground(self, regions=None, diffusion_template=None, document_text="", **kwargs):
        return {
            "source": "local_fallback",
            "regions": regions or [],
            "diffusion_template": diffusion_template,
            "priors": {},
            "notes": [],
        }
