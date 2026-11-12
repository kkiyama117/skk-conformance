"""Record the adapter argv and then run the wrapped fake adapter."""

import os
import sys

record_path = sys.argv[1]
with open(record_path, "w", encoding="utf-8") as stream:
    stream.write("\n".join(sys.argv[2:]))
os.execv(sys.executable, [sys.executable, *sys.argv[2:]])
