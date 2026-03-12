# Scripts - Random Collection of Useful Scripts

### `anonymize`
Anonymizes a text by replacing words with predefined placeholders.

### `fix_broken_symlinks`
Interactively repair broken symlinks using plocate.

```bash
Broken: /home/john/.local/bin/headlinify -> /home/john/some/path/headlinify.py
1) /home/john/some/other/path/headlinify.py
0) Skip
Choose a line number: 1
```

### `genpw`
Generate passwords and usernames from /dev/urandom using 'a-zA-Z0-9-!@#$%^&*()_+~'

```bash
$ genpw 40
L&bGI~96*dx%YbloSWu6%&iLc!r3VHCcyF!%3N4u

$ genpw 10x2 username
Iougleicke
Vaaaaalues
```

### `headlinify`
Apply headline/title-case capitalization to text.

```bash
> ./headlinify "the man with the golden gun"
The man With the Golden Gun
```

### `paste`
A script that pastes text in the currently focussed window.
It is meant to be used by other programs.
It determines the currently focused window and "presses" Ctrl + Shift + V if it's a terminal or Ctrl + V otherwise.

### `pdfreplace`
Find and replace multiple strings in a PDF while trying to preserve the appearance.

### `strconv`
strconv converts a string with spaces and non-ascii into spaceless-ascii.

```bash
$ strconv Die Lösung des Problöms ißt Gemüse
Die_Loesung_des_Probloems_isst_Gemuese
```

---

## Legacy Archive

### `arXiv`
Fetch latest papers from arxiv.org

### `telegram-send`

Sends a file or a message string to a preconfigured Telegram bot.

```bash
telegram-send <file>/This is a long message
```
If the message consists of just one word or path and this word/path refers to an existing file, then a file is send.
Otherwise a message.
