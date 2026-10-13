class AmneziaConfigService:
    """Placeholder for importing and validating AmneziaWG client configs."""

    def expected_allowed_ips(self, lan_cidr: str = "192.168.50.0/24") -> list[str]:
        return [lan_cidr]
