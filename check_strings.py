import json
from datetime import datetime, timezone
from pathlib import Path

TEXT_FILE = Path("strings.txt")
RESULT_FILE = Path("result.json")
LOG_FILE = Path("log.md")


def main():
    text = TEXT_FILE.read_text(encoding="utf-8")

    # If the file contains the letter X (case-insensitive), result is 0.
    result = 0 if "x" in text.lower() else 4

    RESULT_FILE.write_text(
        json.dumps({"result": result}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    log_entry = (
        f"- {datetime.now(timezone.utc).isoformat()} — 执行了此脚本 — "
        f"文件是否发生变化: {'是' if 'x' in text.lower() else '否'}\n"
    )
    with LOG_FILE.open("a", encoding="utf-8") as log:
        log.write(log_entry)

    print(result)


if __name__ == "__main__":
    main()
