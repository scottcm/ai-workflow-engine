from profiles.jpa_mt.jpa_mt_config import JpaMtConfig


class JpaMtProfile:
    def __init__(self, **config):
        model = JpaMtConfig.model_validate(config)
        self.config = model.model_dump()