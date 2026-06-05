from getpass import getpass

from backend.core.password_hashing import make_password_hash


def main() -> int:
    password_1 = getpass("Emergency password: ")
    password_2 = getpass("Confirm emergency password: ")

    if password_1 != password_2:
        print("Passwords do not match.")
        return 1
    if len(password_1) < 12:
        print("Password must be at least 12 characters.")
        return 1

    print(f"PORTAL_EMERGENCY_PASSWORD_HASH={make_password_hash(password_1)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
