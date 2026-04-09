#!/bin/bash
# Remove Link from Codex
set -e

MODE="${1:---project}"

if [ "$MODE" = "--global" ]; then
    TARGET="$HOME/AGENTS.md"
else
    TARGET="AGENTS.md"
fi

if [ ! -f "$TARGET" ]; then echo "No $TARGET found"; exit 0; fi

python3 -c "
import re, os
text = open('$TARGET').read()
cleaned = re.sub(r'\n*## Link — Personal Knowledge Wiki\n.*?(?=\n## |\Z)', '', text, flags=re.DOTALL).rstrip()
if cleaned:
    open('$TARGET', 'w').write(cleaned + '\n')
    print('Link section removed from $TARGET')
else:
    os.remove('$TARGET')
    print('$TARGET was empty after removal — deleted')
"
