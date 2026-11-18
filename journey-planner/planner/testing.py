from django.test.runner import DiscoverRunner


class NoDatabaseTestRunner(DiscoverRunner):
    """The planner has no database; skip Django's database setup."""

    def setup_databases(self, **kwargs):
        return None

    def teardown_databases(self, old_config, **kwargs):
        pass
