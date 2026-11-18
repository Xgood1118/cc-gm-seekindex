import argparse
import seekindex as m


def main():
    ap = argparse.ArgumentParser(description="字节索引与精确 seek")
        ap.add_argument("--at", type=int, required=True)
        ap.add_argument("--out", required=True)
    a = ap.parse_args()
        print("TODO")


if __name__ == "__main__":
    main()
