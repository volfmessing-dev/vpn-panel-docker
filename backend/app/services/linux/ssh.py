class LinuxSshExecutor:
    """Placeholder for future SSH command execution with dry-run support."""

    def health_command(self) -> str:
        return "uname -a && sysctl net.ipv4.ip_forward"
