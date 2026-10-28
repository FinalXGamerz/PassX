"""
Password Generator
Generates VAULTX###### format passwords
"""

import random

def generate_shulker_password() -> str:
    """
    Generate a password in format: VAULTX######
    Where ###### is 6 random digits

    Returns:
        str: Generated password (e.g., "VAULTX123456")
    """
    random_numbers = ''.join([str(random.randint(0, 9)) for _ in range(6)])
    return f"VAULTX{random_numbers}"

def generate_custom_password(prefix: str = "VAULTX", length: int = 6) -> str:
    """
    Generate a custom password with specified prefix and number length

    Args:
        prefix: Password prefix (default: "VAULTX")
        length: Number of random digits (default: 6)

    Returns:
        str: Generated password
    """
    random_numbers = ''.join([str(random.randint(0, 9)) for _ in range(length)])
    return f"{prefix}{random_numbers}"

if __name__ == "__main__":
    # Test password generation
    for i in range(5):
        print(f"Password {i+1}: {generate_VAULTX_password()}")
