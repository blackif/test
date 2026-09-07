import json
from datetime import datetime, timezone
from pathlib import Path

TEXT_FILE = Path("strings.txt")
RESULT_FILE = Path("result.json")
LOG_FILE = Path("log.md")


def main():
    text = TEXT_FILE.read_text(encoding="utf-8")

    # result is 0 when strings.txt contains X/x; otherwise 4.
    result = 0 if "x" in text.lower() else 4

    RESULT_FILE.write_text(
        json.dumps({"result": result}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    # The log status is determined directly from the result.
    file_changed = "否" if result == 0 else "是"

    timestamp = datetime.now(timezone.utc).isoformat()
    log_entry = (
        f"- {timestamp} — 执行了此脚本 — "
        f"文件是否发生变化: {file_changed} -> 结果为 {result}\n"
    )
    with LOG_FILE.open("a", encoding="utf-8") as log:
        log.write(log_entry)

    print(f"result={result}")
    print(f"file_changed={file_changed}")


if __name__ == "__main__":
    main()
