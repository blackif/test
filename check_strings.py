import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

TEXT_FILE = Path("strings.txt")
RESULT_FILE = Path("result.json")
LOG_FILE = Path("log.md")
HASH_FILE = Path(".last_strings_hash")


def main():
    text = TEXT_FILE.read_text(encoding="utf-8")
    current_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

    # result is 0 when strings.txt contains X/x; otherwise 4.
    result = 0 if "x" in text.lower() else 4

    RESULT_FILE.write_text(
        json.dumps({"result": result}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    previous_hash = None
    if HASH_FILE.exists():
        previous_hash = HASH_FILE.read_text(encoding="utf-8").strip()

    if previous_hash is None:
        file_changed = "是（首次执行）"
    else:
        file_changed = "是" if current_hash != previous_hash else "否"

    timestamp = datetime.now(timezone.utc).isoformat()
    log_entry = (
        f"- {timestamp} — 执行了此脚本 — "
        f"文件是否发生变化: {file_changed}\n"
    )
    with LOG_FILE.open("a", encoding="utf-8") as log:
        log.write(log_entry)

    HASH_FILE.write_text(current_hash + "\n", encoding="utf-8")

    print(f"result={result}")
    print(f"file_changed={file_changed}")


if __name__ == "__main__":
    main()
