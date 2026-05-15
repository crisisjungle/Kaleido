class _NoopUpdater:
    def add_action(self, *args, **kwargs):
        return None

    def stop(self):
        return None


class ZepGraphMemoryManager:
    _updaters = {}

    @classmethod
    def create_updater(cls, simulation_id, graph_id):
        updater = _NoopUpdater()
        cls._updaters[simulation_id] = updater
        return updater

    @classmethod
    def get_updater(cls, simulation_id):
        return cls._updaters.get(simulation_id)

    @classmethod
    def stop_updater(cls, simulation_id):
        updater = cls._updaters.pop(simulation_id, None)
        if updater:
            updater.stop()

    @classmethod
    def stop_all(cls):
        for updater in list(cls._updaters.values()):
            updater.stop()
        cls._updaters.clear()
