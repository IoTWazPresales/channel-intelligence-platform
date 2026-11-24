"""Discovery V2: find a customer's web shops, their product pages, and link them.

Pure functions take an injected ``getter`` (the polite getter), ``search`` and ``resolve`` (DNS), so
unit tests never reach the network. Nothing here names a customer, retailer, domain or country:
the tenant's country, domain endings and search providers come only from tenant settings, and a
missing setting makes Discover refuse (``settings_missing``).

Preview writes nothing (a READ ONLY database transaction). Apply writes exactly what the user
reviewed, on an explicit user action. The scheduled beat path (``scheduled.run_scheduled_reporting_discovery``)
previews then applies auto-linked sites and queues the rest — only when ``discovery.schedule_enabled`` is on.
"""
