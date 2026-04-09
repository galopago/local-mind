#!/bin/bash
# Remove Link from Copilot
set -e

TARGET=".github/copilot-instructions.md"
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
