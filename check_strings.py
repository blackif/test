import json
from pathlib import Path

TEXT_FILE = Path("strings.txt")
RESULT_FILE = Path("result.json")


def main():
    text = TEXT_FILE.read_text(encoding="utf-8")

    # If the file contains the letter X (case-insensitive), result is 0.
    result = 0 if "x" in text.lower() else 4

    RESULT_FILE.write_text(
        json.dumps({"result": result}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(result)


if __name__ == "__main__":
    main()
