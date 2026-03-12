#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS] [DIR]

Interactively repair broken symlinks using plocate.

Options:
  -e PATTERN  Exclude paths matching PATTERN (repeatable, passed to find -path)
  -l          List broken symlinks and exit
  -h          Show this help message

Arguments:
  DIR         Directory to search (default: current directory)

Examples:
  $(basename "$0") -e '*/.git' -e '*/node_modules' ~
EOF
}

LIST_ONLY=false
EXCLUDES=(
  "${HOME}/.local/share/Trash"
  "*/.Trash-$(id -u)"
  "${HOME}/.local/share/flatpak"
)

while getopts "lhe:" opt; do
  case "$opt" in
    l) LIST_ONLY=true ;;
    h) usage; exit 0 ;;
    e) EXCLUDES+=("$OPTARG") ;;
    *) usage; exit 1 ;;
  esac
done
shift $((OPTIND - 1))

SEARCH_DIR="$(realpath -- "${1:-$PWD}")"

FIND_PRUNE=()
for excl in "${EXCLUDES[@]}"; do
  FIND_PRUNE+=(-path "$excl" -prune -o)
done

if $LIST_ONLY; then
  find "$SEARCH_DIR" "${FIND_PRUNE[@]}" -xtype l -print
  exit 0
fi

while IFS= read -r -d '' link; do
  broken_target="$(readlink -- "$link" || true)"
  filename="$(basename -- "$broken_target")"

  mapfile -t matches < <(plocate -- "$filename" 2>/dev/null | grep -vE '(^|/)\.' || true)

  echo
  echo "Broken: $link -> $broken_target"

  if ((${#matches[@]} == 0)); then
    echo "No plocate matches for: $filename (skipping)"
    continue
  fi

  for i in "${!matches[@]}"; do
    printf '  %d) %s\n' "$((i+1))" "${matches[$i]}"
  done
  echo "  0) Skip"

  while :; do
    read -r -p "Choose a line number: " choice < /dev/tty

    if ! [[ "$choice" =~ ^[0-9]+$ ]]; then
      echo "Please enter a number."
      continue
    fi

    if (( choice == 0 )); then
      echo "Skipped."
      break
    fi

    if (( choice >= 1 && choice <= ${#matches[@]} )); then
      new_target="${matches[$((choice-1))]}"
      ln -Tfs -- "$new_target" "$link"
      echo "Fixed: $link -> $new_target"
      break
    fi

    echo "Out of range (1..${#matches[@]} or 0 to skip)."
  done
done < <(find "$SEARCH_DIR" "${FIND_PRUNE[@]}" -xtype l -print0)
