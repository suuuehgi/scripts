# Scripts - Random Collection of Useful Scripts

### genpw
Generate passwords and usernames from /dev/{u,}random using 'a-zA-Z0-9-!@#$%^&*()_+~'

```bash
$ genpw 40
L&bGI~96*dx%YbloSWu6%&iLc!r3VHCcyF!%3N4u

$ genpw 10x2 username
Iougleicke
Vaaaaalues
```

### strconv
strconv converts a string with spaces and non-ascii into spaceless-ascii.

```bash
$ strconv Die Lösung des Problöms ißt Gemüse
Die_Loesung_des_Probloems_isst_Gemuese
```

---

## Legacy Archive

### arXiv
Fetch latest papers from arxiv.org

### telegram-send

Sends a file or a message string to a preconfigured Telegram bot.

```bash
telegram-send <file>/This is a long message
```
If the message consists of just one word or path and this word/path refers to an existing file, then a file is send.
Otherwise a message.
