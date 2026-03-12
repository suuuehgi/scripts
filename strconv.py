#!/usr/bin/python3
# Version: 2

# 2: isinstance() instead of type(); simplified help check; print help when called without args

import sys, os

def strconv(string):
    if isinstance(string, list):
        string = " ".join(string)
    elif isinstance(string, str):
        pass
    else:
        raise RuntimeError("Need a list or str, not %s!" % type(string))

    translate = {
        ' ':  '_',
        'ß': 'ss',
        'ä': 'ae',
        'ö': 'oe',
        'ü': 'ue',
        'Ä': 'Ae',
        'Ö': 'Oe',
        'Ü': 'Ue',
        "'":  '',
    }

    for key, value in translate.items():
        string = string.replace(key, value)

    string = string.encode('utf-8', 'surrogateescape').decode('ascii', 'ignore')

    return string

if __name__ == "__main__":
    name = os.path.basename(sys.argv[0])

    if len(sys.argv) == 1 or any(arg in sys.argv for arg in ('-h', '--help')):
        print("{program} converts a string with spaces and non-ASCII into spaceless ASCII.\n".format(program=name))
        print("Usage: {program} \"<string>\"\n".format(program=name))
        print("\t-h, --help: Print help")
    else:
        print(strconv(sys.argv[1:]))
