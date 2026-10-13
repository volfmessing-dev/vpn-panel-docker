class MikroTikClient:
    """Placeholder for RouterOS API/SSH integration."""

    def preview_bypass_rules(self, address_list_name: str = "bypass") -> list[str]:
        return [
            f"/ip firewall mangle add chain=prerouting dst-address-list={address_list_name} "
            "action=mark-routing new-routing-mark=to-ru-cloud passthrough=no",
            "/ip route add dst-address=0.0.0.0/0 gateway=wg-ru-cloud routing-table=to-ru-cloud",
        ]
