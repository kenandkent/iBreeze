from ibreeze import build_info


def main() -> None:
    info = build_info()
    print(f"{info['app']} protocol v{info['protocol_version']}")


if __name__ == "__main__":
    main()
