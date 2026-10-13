import subprocess


def generate_private_key() -> str:
    completed = subprocess.run(["wg", "genkey"], capture_output=True, check=True, text=True)
    return completed.stdout.strip()


def public_key(private_key: str) -> str:
    completed = subprocess.run(
        ["wg", "pubkey"],
        input=f"{private_key}\n",
        capture_output=True,
        check=True,
        text=True,
    )
    return completed.stdout.strip()
