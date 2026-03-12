#!/bin/bash
# Version: 6

# 2: Added "safe" for random
# 3: Added x syntax
# 4: Added "alpha"
# 5: Fixed byte reading, quoting, input validation; simplified alpha/number modes, dropped "safe" mode (/dev/random == /dev/urandom on Linux 5.6+)

HELP="Generate password from /dev/urandom\n
\tUsage:\t$0 [NxM] [alpha|readable|number|username]\n\n
\t -h/--help:\tThis Text\n
\talpha:\t\tAlphanumeric string (a-zA-Z0-9)\n
\treadable:\tReplace -!@#\$%^&*()_+~ and 0-9 with vowels\n
\tnumber:\t\tCreate a numeric string\n
\tusername:\tSame as readable but with uppercase first letter only\n\n
Example:\n
\t$0 8x5 username"

if [[ -z "$1" ]]; then
    echo -e "$HELP"
    exit 1
elif [[ "$1" == '-h' || "$1" == '--help' ]]; then
    echo -e "$HELP"
    exit 0
fi

if [[ "$1" =~ x ]]; then
    LENGTH=$(echo "$1" | cut -d 'x' -f 1)
    N=$(echo "$1" | cut -d 'x' -f 2)
else
    LENGTH=$1
    N=1
fi

if ! [[ "$LENGTH" =~ ^[0-9]+$ ]] || ! [[ "$N" =~ ^[0-9]+$ ]]; then
    echo "Error: invalid format '$1'" >&2
    exit 1
fi

# Factor 10 gives ~2.7x the needed characters for the default charset (~70/256 bytes survive).
# number mode uses factor 50 because only ~10/256 bytes survive tr -dc '0-9'.
BYTES=$(( LENGTH * N * 10 ))

if [[ $# == 1 ]]; then
    head -c "$BYTES" /dev/urandom | tr -dc 'a-zA-Z0-9-!@#$%^&*()_+~' | fold -w "$LENGTH" | head -n "$N"

elif [[ $# == 2 ]]; then

    if [[ "$2" == "alpha" ]]; then
        head -c "$BYTES" /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w "$LENGTH" | head -n "$N"

    elif [[ "$2" == "number" ]]; then
        head -c $(( LENGTH * N * 50 )) /dev/urandom | tr -dc '0-9' | fold -w "$LENGTH" | head -n "$N"

    elif [[ "$2" == "username" ]]; then
        head -c "$BYTES" /dev/urandom \
            | tr -dc 'a-zA-Z0-9-!@#$%^&*()_+~' \
            | fold -w "$LENGTH" \
            | head -n "$N" \
            | sed 'y/-!@#$%^&*()_+~0123456789/aeiouaeiouaeioaeiouaeiou/' \
            | while IFS= read -r word; do
                echo "$(tr '[:lower:]' '[:upper:]' <<< "${word:0:1}")$(tr '[:upper:]' '[:lower:]' <<< "${word:1}")"
              done

    elif [[ "$2" == "readable" ]]; then
        head -c "$BYTES" /dev/urandom \
            | tr -dc 'a-zA-Z0-9-!@#$%^&*()_+~' \
            | fold -w "$LENGTH" \
            | head -n "$N" \
            | sed 'y/-!@#$%^&*()_+~0123456789/aeiouaeiouaeioaeiouaeiou/'
        echo "https://imgs.xkcd.com/comics/password_strength.png"

    else
        # Treat $2 as additional characters to include in the charset
        head -c "$BYTES" /dev/urandom | tr -dc "a-zA-Z0-9$2" | fold -w "$LENGTH" | head -n "$N"
    fi

else
    echo -e "$HELP"
    exit 1
fi
